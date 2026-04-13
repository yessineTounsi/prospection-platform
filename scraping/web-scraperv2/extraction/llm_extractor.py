"""
extraction/llm_extractor.py — Phase 6 : Extraction LLM en un seul appel
========================================================================
Envoie TOUT le contenu scrapé (welcome + secondary_data) à Ollama
et extrait les 9 champs en une seule requête JSON.

  company_name    — nom exact de l'entreprise
  description     — résumé de l'activité (2-3 phrases)
  services        — liste des services / produits / offres
  clients         — liste des clients / références
  team_leaders    — liste des dirigeants avec nom + titre
  founded_year    — année de fondation (entier)
  employees_count — effectif ou fourchette ("50+", "200-500")
  revenue         — chiffre d'affaires ou fourchette si disponible
  reviews         — liste des témoignages clients

Input  : company avec welcome_data + secondary_data
Output : company enrichi avec les 9 champs remplis
"""

import json
import logging
import re
import requests

from config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_PROMPT_TEMPLATE = """\
Tu es un expert en extraction de données B2B.
Voici le contenu complet d'un site web d'entreprise (pages welcome + about + services + clients + team + contact + partners).

Extrais UNIQUEMENT les informations explicitement présentes dans le texte.
Ne devine pas, ne calcule pas, ne suppose pas.
Si une information est absente, utilise null.

Réponds UNIQUEMENT avec un JSON valide dans ce format exact :
{{
  "company_name": "Nom exact de l'entreprise",
  "description": "Résumé de l'activité en 2-3 phrases",
  "services": ["service 1", "service 2", "..."],
  "clients": ["Client 1", "Client 2", "..."],
  "team_leaders": [{{"name": "Prénom Nom", "title": "Titre"}}],
  "founded_year": 2019,
  "employees_count": "50+",
  "revenue": "100M€",
  "reviews": ["témoignage 1", "témoignage 2"]
}}

Règles strictes :
- company_name : le nom officiel de l'entreprise (pas le domaine URL)
- description : uniquement basée sur le texte "about" ou la page d'accueil
- services : liste des vrais services/produits (pas les éléments de navigation)
- clients : noms d'entreprises clientes explicitement mentionnées
- team_leaders : uniquement les personnes nommées avec leur titre
- founded_year : uniquement si une année EXACTE est mentionnée (ex: "founded in 2019") — sinon null
- employees_count : nombre ou fourchette explicite (ex: "700+", "50-100") — sinon null
- revenue : chiffre d'affaires explicite — sinon null
- reviews : citations textuelles de témoignages clients avec le nom de la personne

CONTENU DU SITE :
{content}

JSON:"""


# ── Construction du contexte complet ──────────────────────────────────────────

# Regex pour supprimer les menus de navigation répétitifs en début de page
_NAV_HEADER = re.compile(
    r'^(?:(?:Skip to (?:content|main)|Home\s*[>\|]|'
    r'(?:Capital Markets|Insurance|Banking|Solutions|Products|Services|'
    r'Company|About|Contact|Partners|Resources|News|Blog)\s*(?:Close|Open)?'
    r'\s*(?:Capital Markets|Insurance|Banking|Solutions|Products|Services|'
    r'Company|About|Contact|Partners|Resources|News|Blog)?\s*)+\s*){2,}',
    re.IGNORECASE | re.DOTALL
)

_NAV_LINE = re.compile(
    r'^(?:Skip to (?:content|main)|'
    r'(?:Capital Markets|Insurance|Banking|Solutions|Products|Services|'
    r'Company|About|Contact|Partners|Resources|News|Blog|'
    r'Technology|Platform|Clients|Team|Management|Leadership|'
    r'Careers|Events|Press|Media)\s*(?:Close|Open)?\s*[>\|]?\s*){3,}$',
    re.IGNORECASE
)


def _strip_nav_header(text: str) -> str:
    """
    Supprime le bloc de navigation répétitif en début de page.

    Gère deux formats :
    - Texte compact une seule ligne (ex: Vermeg) : cherche "Careers Home [mot]"
      qui marque la fin du nav et le début du contenu réel (breadcrumb).
    - Texte multi-lignes : supprime les lignes nav initiales ligne par ligne.
    """
    if not text:
        return text

    # ── Cas 1 : texte compact (tout sur une ou très peu de lignes) ────────────
    # Les pages secondaires Vermeg terminent leur nav dupliqué par "Careers Home"
    # suivi du breadcrumb, ex: "Careers Home About us Leadership Meet our leaders"
    m = re.search(r'\bCareers\s+Home\b', text)
    if m and m.start() > 300:
        home_idx = text.index('Home', m.start())
        return text[home_idx:].strip()

    # ── Cas 2 : multi-lignes — suppression ligne par ligne ────────────────────
    lines = text.split('\n')
    nav_end = 0
    for i, line in enumerate(lines[:20]):
        stripped = line.strip()
        if not stripped:
            continue
        if _NAV_LINE.match(stripped):
            nav_end = i + 1
        elif nav_end > 0:
            break
    return '\n'.join(lines[nav_end:]).strip()


def _build_context(company: dict, max_chars: int = 16000) -> str:
    """
    Concatène tout le contenu disponible : welcome_data + secondary_data.
    Supprime les headers de navigation répétitifs.
    Limite à max_chars pour ne pas dépasser la fenêtre du modèle.
    """
    parts = []

    # Page d'accueil
    wd = company.get("welcome_data", {})
    if wd and wd.get("clean_text"):
        parts.append("[PAGE ACCUEIL]\n" + wd["clean_text"])

    # Pages secondaires (dans l'ordre de pertinence)
    # leadership/management ajoutés pour capturer les dirigeants
    priority = [
        "about", "services", "clients", "team",
        "leadership", "management",
        "technology", "partners", "contact",
    ]
    sd = company.get("secondary_data", {})

    # Pages prioritaires d'abord
    for page in priority:
        if page in sd and isinstance(sd[page], dict):
            text = sd[page].get("clean_text", "")
            if text:
                text = _strip_nav_header(text)
                if text:
                    parts.append(f"[PAGE {page.upper()}]\n{text}")

    # Pages restantes
    for page, data in sd.items():
        if page not in priority and isinstance(data, dict):
            text = data.get("clean_text", "")
            if text:
                text = _strip_nav_header(text)
                if text:
                    parts.append(f"[PAGE {page.upper()}]\n{text}")

    full_context = "\n\n".join(parts)

    # Tronquer si trop long
    if len(full_context) > max_chars:
        full_context = full_context[:max_chars] + "\n[... contenu tronqué ...]"

    return full_context


# ── Appel Ollama ───────────────────────────────────────────────────────────────

def _call_ollama(context: str) -> dict | None:
    prompt = _PROMPT_TEMPLATE.format(content=context)
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
        return _parse_response(raw)
    except requests.exceptions.ConnectionError:
        logger.error("Ollama inaccessible — " + OLLAMA_URL)
        return None
    except Exception as e:
        logger.error("Erreur Ollama : " + str(e))
        return None


def _parse_response(raw: str) -> dict | None:
    """Parse la réponse JSON d'Ollama."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback : extraire le JSON du texte
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ── Post-processing ────────────────────────────────────────────────────────────

def _clean_result(result: dict) -> dict:
    """Nettoie et valide les valeurs extraites par le LLM."""

    # company_name : string propre
    if isinstance(result.get("company_name"), str):
        result["company_name"] = result["company_name"].strip()

    # description : forcer string (pas une liste)
    if isinstance(result.get("description"), list):
        result["description"] = " ".join(str(v).strip() for v in result["description"] if v)
    elif isinstance(result.get("description"), str):
        result["description"] = result["description"].strip()

    # services : liste de strings non vides
    if isinstance(result.get("services"), list):
        result["services"] = [s.strip() for s in result["services"] if isinstance(s, str) and len(s.strip()) > 2]
        if not result["services"]:
            result["services"] = None

    # clients : liste propre
    if isinstance(result.get("clients"), list):
        result["clients"] = [c.strip() for c in result["clients"] if isinstance(c, str) and len(c.strip()) > 1]
        if not result["clients"]:
            result["clients"] = None

    # team_leaders : liste de dicts {name, title}
    if isinstance(result.get("team_leaders"), list):
        cleaned = []
        for item in result["team_leaders"]:
            if isinstance(item, dict) and item.get("name"):
                cleaned.append({
                    "name":  str(item.get("name", "")).strip(),
                    "title": str(item.get("title", "")).strip(),
                })
        result["team_leaders"] = cleaned if cleaned else None

    # founded_year : entier uniquement
    fy = result.get("founded_year")
    if fy is not None:
        try:
            result["founded_year"] = int(fy)
        except (ValueError, TypeError):
            result["founded_year"] = None

    # employees_count : string
    if isinstance(result.get("employees_count"), (int, float)):
        result["employees_count"] = str(result["employees_count"])

    # reviews : liste de strings
    if isinstance(result.get("reviews"), list):
        result["reviews"] = [r.strip() for r in result["reviews"] if isinstance(r, str) and len(r.strip()) > 10]
        if not result["reviews"]:
            result["reviews"] = None

    return result


# ── Extraction principale ──────────────────────────────────────────────────────

_FIELDS = ["company_name", "description", "services", "clients",
           "team_leaders", "founded_year", "employees_count", "revenue", "reviews"]


def extract_null_fields(company: dict) -> dict:
    """
    Phase 6 : Envoie tout le contenu scrapé à Ollama en un seul appel
    et remplit les champs null.

    Args:
        company : Dict entreprise avec welcome_data + secondary_data

    Returns:
        company enrichi
    """
    fields_to_extract = [f for f in _FIELDS if company.get(f) is None]

    if not fields_to_extract:
        logger.info("  Tous les champs déjà remplis — LLM extractor ignoré")
        return company

    logger.info(f"  Phase 6 — Extraction LLM ({len(fields_to_extract)} champs en 1 appel)")

    context = _build_context(company)
    if not context.strip():
        logger.warning("  Aucun contenu disponible pour l'extraction")
        return company

    logger.info(f"  Contexte : {len(context)} caractères")

    result = _call_ollama(context)
    if not result:
        logger.error("  Ollama n'a pas retourné de résultat")
        return company

    result = _clean_result(result)

    # Appliquer uniquement les champs qui étaient null
    filled = 0
    for field in fields_to_extract:
        value = result.get(field)
        if value is not None and value != "" and value != []:
            company[field] = value
            filled += 1
            logger.info(f"  [{field}] ✓ {str(value)[:80]}")
        else:
            logger.warning(f"  [{field}] Non trouvé")

    logger.info(f"  {filled}/{len(fields_to_extract)} champs extraits")
    return company
