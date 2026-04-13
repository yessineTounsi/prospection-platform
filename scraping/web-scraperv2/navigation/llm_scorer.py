"""
navigation/llm_scorer.py
========================
Remplace link_scorer.py — utilise Ollama (LLM local) pour classer
les liens internes en catégories B2B.

Avantages vs paraphrase-multilingual-MiniLM-L12-v2 :
  - Comprend le contexte (texte + URL + entourage)
  - Bilingue FR/EN natif, pas de faux positifs par similarité cosinus
  - Zéro dépendance sentence-transformers / numpy

Interface identique à link_scorer.py (remplacement drop-in) :
  LLMScorer().score_links(links, top_k, max_per_cat) → list[ScoredLink]
  scored_links_to_dict(results)       → {cat: url}
  scored_links_to_rich_dict(results)  → dict enrichi
"""

import json
import logging
import requests
from dataclasses import dataclass

from navigation.categories  import CATEGORIES, CATEGORIES_BY_NAME
from navigation.link_extractor import ExtractedLink
from config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    SCORER_TOP_K, SCORER_MAX_PER_CAT,
)

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {c.name for c in CATEGORIES} | {"none"}

# ── Prompt ─────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
Tu es un classificateur de liens web pour un pipeline de prospection B2B.

Catégories disponibles :
  about       — présentation entreprise, histoire, mission, gouvernance, actionnaires, rapport annuel
  team        — équipe, dirigeants, management, comité de direction, recrutement, carrières
  services    — offres, produits, solutions, expertises, catalogue de services, métiers
  clients     — références, cas clients, témoignages, portfolio, réalisations
  contact     — nous contacter, adresse, bureaux, siège, formulaire de contact, agences
  technology  — stack technique, cloud, cybersécurité, DevOps, infrastructure IT, observabilité
  partners    — partenaires, certifications éditeurs, écosystème, alliances
  none        — page inutile : login, panier, CGU, cookies, sitemap, mentions légales, 404...

Règles strictes :
  1. Chaque lien reçoit exactement UNE catégorie (ou "none").
  2. Utilise le texte du lien ET le slug de l'URL pour décider.
  3. Si le lien est ambigu entre deux catégories, choisis la priorité la plus haute :
     about > team > services > clients > contact > technology > partners
  4. Réponds UNIQUEMENT en JSON valide — aucun texte autour.
"""


def _build_prompt(links: list) -> str:
    lines = []
    for i, link in enumerate(links):
        text    = link.text.strip()    or "(sans texte)"
        slug    = link.url_slug.strip() or "(sans slug)"
        context = link.context.strip()[:80] if link.context else ""
        entry   = f'{i}: texte="{text}" | slug="{slug}"'
        if context:
            entry += f' | contexte="{context}"'
        lines.append(entry)

    n = len(links)
    example = ", ".join(f'"{i}": "about"' for i in range(min(3, n)))

    return (
        _SYSTEM_PROMPT
        + "\nLiens à classifier :\n"
        + "\n".join(lines)
        + f'\n\nIMPORTANT: Réponds UNIQUEMENT avec un objet JSON contenant exactement {n} clés.'
        + f'\nLes clés sont les indices 0 à {n-1} en string, les valeurs sont les catégories.'
        + f'\nExemple de format EXACT attendu: {{{example}, ...}}'
        + f'\nJSON:'
    )


# ── Appel Ollama ───────────────────────────────────────────────────────────────

def _call_ollama(prompt: str) -> dict | None:
    """
    Envoie le prompt à Ollama et retourne le dict JSON parsé.
    Retourne None en cas d'erreur.
    """
    try:
        response = requests.post(
            OLLAMA_URL.rstrip("/") + "/api/generate",
            json={
                "model":   OLLAMA_MODEL,
                "prompt":  prompt,
                "format":  "json",
                "stream":  False,
                "options": {"temperature": 0.0},
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
        logger.debug("Ollama raw response : " + raw[:200])
        return raw  # parsing fait dans score_links via _parse_classification

    except requests.exceptions.ConnectionError:
        logger.error("Ollama inaccessible — vérifie que le service tourne sur " + OLLAMA_URL)
        return None
    except json.JSONDecodeError as e:
        logger.error("Réponse Ollama non-JSON : " + str(e))
        return None
    except Exception as e:
        logger.error("Erreur Ollama : " + str(e))
        return None


def _parse_classification(raw: str, n_links: int) -> dict | None:
    """
    Parse robuste — gère les cas où Mistral enveloppe la réponse
    dans une clé intermédiaire ou ajoute du texte autour.
    """
    if not raw:
        return None

    # Cas 1 : JSON direct {"0": "about", ...}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            # Vérifier si les clés sont bien des indices
            if any(str(i) in data for i in range(n_links)):
                return data
            # Cas où Mistral enveloppe : {"classification": {"0": ...}}
            for v in data.values():
                if isinstance(v, dict) and any(str(i) in v for i in range(n_links)):
                    return v
    except json.JSONDecodeError:
        pass

    # Cas 2 : Extraire le JSON depuis le texte brut
    import re
    match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ── Règles regex — classification directe pour URLs claires ───────────────────

# Chaque règle : (liste de mots-clés dans slug/texte, catégorie)
# Priorité : première règle qui matche gagne
_REGEX_RULES = [
    (["about", "a-propos", "qui-sommes", "story", "histoire",
      "mission", "vision", "gouvernance", "presentation",
      "company", "entreprise"],                                      "about"),
    (["team", "equipe", "direction", "management", "leadership",
      "dirigeant", "career", "careers", "carriere", "emploi",
      "recrutement"],                                                "team"),
    (["service", "solution", "offre", "produit", "expertise",
      "prestation", "catalog"],                                      "services"),
    (["customer", "client", "reference", "cas-client", "temoignage",
      "portfolio", "realisations", "success"],                       "clients"),
    (["contact", "nous-joindre", "location", "bureau", "agence",
      "siege", "adresse"],                                           "contact"),
    (["technology", "tech", "stack", "cloud", "devops", "infra",
      "cyber", "securite", "observ"],                                "technology"),
    (["partner", "partenaire", "certification", "ecosystem",
      "alliance"],                                                   "partners"),
]


def _regex_classify(link) -> str | None:
    """
    Tente de classifier un lien par règles regex sur slug + texte.
    Retourne la catégorie ou None si aucune règle ne matche.
    """
    combined = (link.url_slug + " " + link.text).lower()
    for keywords, category in _REGEX_RULES:
        if any(kw in combined for kw in keywords):
            return category
    return None


# ── Structures de résultat ─────────────────────────────────────────────────────

@dataclass
class ScoredLink:
    link:       ExtractedLink
    category:   str
    score:      float
    all_scores: dict


# ── Scorer principal ───────────────────────────────────────────────────────────

class LLMScorer:
    """
    Scorer basé sur LLM Ollama.
    Charge aucun modèle ML — tout passe par l'API REST Ollama.
    """

    def score_links(
        self,
        links:       list,
        top_k:       int = None,
        max_per_cat: int = None,
        base_url:    str = None,
    ) -> list:
        """
        Classe les liens par catégorie via Ollama.

        Args:
            links       : liste d'ExtractedLink (sortie de link_extractor)
            top_k       : nombre max de liens à retourner
            max_per_cat : nombre max de liens par catégorie

        Returns:
            Liste de ScoredLink triés par priorité de catégorie
        """
        if not links:
            return []

        top_k       = top_k       or SCORER_TOP_K
        max_per_cat = max_per_cat or SCORER_MAX_PER_CAT

        logger.info(f"  LLM scorer — {len(links)} liens à classifier (modèle: {OLLAMA_MODEL})")

        all_scored  = []
        llm_pending = []  # liens non résolus par regex → envoyés à Ollama

        # ── Étape 1 : Règles regex (rapide, fiable) ────────────────────────────
        base_domain = base_url.split("/")[2].replace("www.", "") if base_url else ""

        # Normaliser le base_url pour détecter les liens homepage
        base_url_clean = base_url.rstrip("/") if base_url else ""

        # Segments à exclure — articles, actualités, CGU, etc.
        _EXCLUDE_SEGMENTS = re.compile(
            r'/(?:news|blog|blogs|press|actualite|article|post|insight|event|'
            r'newsletter|rapport|report|cgu|terms|privacy|cookie|legal|sitemap)/',
            re.IGNORECASE
        )

        for link in links:
            # Exclure les sous-domaines (ex: vision.confoline.com ≠ confoline.com)
            if base_domain:
                from urllib.parse import urlparse
                link_domain = urlparse(link.url).netloc.replace("www.", "")
                if link_domain != base_domain:
                    logger.info(f"  [skip] domaine différent : {link.url}")
                    continue
            # Exclure les articles/news/blog (ex: /news/eurex-joins-...)
            if _EXCLUDE_SEGMENTS.search(link.url):
                logger.info(f"  [skip] article/news : {link.url}")
                continue
            # Exclure les liens qui pointent vers la homepage (ancres #xxx perdues)
            if base_url_clean and link.url.rstrip("/") == base_url_clean:
                logger.info(f"  [skip] lien homepage : {link.url}")
                continue
            cat = _regex_classify(link)
            if cat:
                logger.info(f"  [regex] [{cat}] {link.url}")
                all_scored.append(ScoredLink(
                    link       = link,
                    category   = cat,
                    score      = 1.0,           # score max — règle certaine
                    all_scores = {cat: 1.0},
                ))
            else:
                llm_pending.append(link)

        logger.info(f"  {len(all_scored)} classifiés par regex, {len(llm_pending)} envoyés à Ollama")

        # ── Étape 2 : Ollama pour les liens ambigus ────────────────────────────
        batch_size = 40
        for batch_start in range(0, len(llm_pending), batch_size):
            batch = llm_pending[batch_start: batch_start + batch_size]
            prompt     = _build_prompt(batch)
            raw        = _call_ollama(prompt)
            classified = _parse_classification(raw, len(batch)) if raw else None

            if not classified:
                logger.warning(f"  Batch {batch_start}–{batch_start+len(batch)} : Ollama sans réponse valide")
                logger.warning(f"  Réponse brute : {str(raw)[:300]}")
                continue

            for local_idx, link in enumerate(batch):
                raw_cat = classified.get(str(local_idx), "none")
                cat     = raw_cat.strip().lower()

                if cat not in VALID_CATEGORIES or cat == "none":
                    continue

                logger.info(f"  [llm]   [{cat}] {link.url}")
                all_scored.append(ScoredLink(
                    link       = link,
                    category   = cat,
                    score      = 0.92,
                    all_scores = {cat: 0.92},
                ))

        # ── Tri par priorité de catégorie ──────────────────────────────────────
        all_scored.sort(key=lambda s: CATEGORIES_BY_NAME[s.category].priority)

        # ── Limite max_per_cat ─────────────────────────────────────────────────
        results, cat_counts = [], {}
        for s in all_scored:
            count = cat_counts.get(s.category, 0)
            if count < max_per_cat:
                results.append(s)
                cat_counts[s.category] = count + 1

        logger.info(f"  {len(results)} pages sélectionnées : {list(cat_counts.keys())}")
        return results[:top_k]


# ── Fonctions utilitaires (interface identique à link_scorer.py) ───────────────

def scored_links_to_dict(results: list) -> dict:
    """Retourne {categorie: url} — prend le PREMIER lien par catégorie (score le plus élevé)."""
    out = {}
    for r in results:
        if r.category not in out:   # garde la première occurrence (meilleur score)
            out[r.category] = r.link.url
    return out


def scored_links_to_rich_dict(results: list) -> dict:
    """Retourne un dict enrichi avec url, texte, score, source — premier lien par catégorie."""
    out = {}
    for r in results:
        if r.category not in out:
            out[r.category] = {
                "url":         r.link.url,
                "link_text":   r.link.text,
                "score":       r.score,
                "source_page": r.link.source_page,
            }
    return out


# ── Singleton (évite de recréer l'objet à chaque appel) ───────────────────────

_scorer = None

def score_links(links: list, top_k: int = None, max_per_cat: int = None) -> list:
    """Fonction standalone avec singleton interne."""
    global _scorer
    if _scorer is None:
        _scorer = LLMScorer()
    return _scorer.score_links(links, top_k=top_k, max_per_cat=max_per_cat)
