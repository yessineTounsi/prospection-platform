"""
cleaner.py — Nettoyage des articles scrapés pour pipeline NLP.

Chaque article nettoyé contient UNIQUEMENT :
    - titre
    - url
    - source
    - date_publication
    - langue
    - auteur
    - extrait
    - texte_complet
    - nlp_ready
    - nlp_missing
    - nlp_text_length

Champs supprimés :
    mots_cles, categories_detectees, relevance_score, relevance_info,
    company_in_title, company_count_in_text, negative_hits, has_full_text,
    source_type, date_rss, titre_rss, source_rss, article_type, date_scraping

Nettoyages appliqués :
    - Suppression des placeholders de template : {ap}, {dp}, {av}, {v2}…
    - Suppression du HTML résiduel et des entités (&amp; etc.)
    - Suppression des URLs inline
    - Suppression des lignes de bruit (navigation, cookie, footer…)
    - Normalisation des espaces et sauts de ligne
    - Normalisation de la date vers YYYY-MM-DD
    - Re-détection fiable de la langue

Usage :
    python cleaner.py
    → lit  articles_only_result.json
    → écrit articles_cleaned.json + articles_cleaned.csv
"""

import re
import os
import json
import csv
import html
from urllib.parse import urlparse
from dateutil import parser as dateparser   # pip install python-dateutil


# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

INPUT_JSON  = "articles_only_result.json"
OUTPUT_JSON = "articles_cleaned.json"
OUTPUT_CSV  = "articles_cleaned.csv"

MIN_TEXT_LENGTH = 100

# Champs à conserver dans l'output final (dans cet ordre)
KEEP_FIELDS = [
    "company_name",     # ← nom de l'entreprise en premier pour identification
    "titre",
    "url",
    "source",
    "date_publication",
    "langue",
    "auteur",
    "extrait",
    "texte_complet",
    "nlp_ready",
    "nlp_missing",
    "nlp_text_length",
]

NLP_REQUIRED = ["url", "texte_complet", "langue"]


# ─────────────────────────────────────────────
#  NETTOYAGE DU TEXTE
# ─────────────────────────────────────────────

# Placeholders de template du type {ap}, {dp}, {av}, {v2}, {pays_citoyens}…
_RE_PLACEHOLDERS   = re.compile(r"\{[^}]{1,30}\}")
_RE_HTML_TAGS      = re.compile(r"<[^>]+>")
_RE_HTML_ENTITIES  = re.compile(r"&[a-zA-Z#0-9]{1,10};")
_RE_INLINE_URLS    = re.compile(r"https?://\S+")
_RE_CTRL_CHARS     = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RE_MULTI_NEWLINE  = re.compile(r"\n{3,}")
_RE_MULTI_SPACE    = re.compile(r" {2,}")
_RE_REPEATED_CHARS = re.compile(r"([^\w\s])\1{2,}")

_NOISE_PATTERNS = re.compile(
    r"(cookie policy|privacy policy|terms of (use|service)|all rights reserved"
    r"|subscribe to our newsletter|click here to|read more|share this article"
    r"|follow us on|©\s*\d{4}|javascript is (disabled|required)"
    r"|select your country|new articles\s*:|top \d+ articles"
    r"|← previous|next →|\(current\))",
    re.IGNORECASE
)

# Lignes qui ressemblent à des noms de pays (navigation goafricaonline)
_RE_COUNTRY_LINE = re.compile(
    r"^(Algeria|Angola|Benin|Botswana|Burkina Faso|Cameroon|Central African Republic"
    r"|Congo|Côte d'Ivoire|Djibouti|Egypt|Ethiopia|Gabon|Ghana|Guinea|Kenya|Liberia"
    r"|Madagascar|Malawi|Mali|Mauritius|Morocco|Mozambique|Namibia|Niger|Nigeria"
    r"|Senegal|Somalia|South Africa|Tanzania|Togo|Tunisia|Uganda|Afrique)$",
    re.IGNORECASE
)


def clean_text_for_nlp(raw: str) -> str:
    """Nettoie un texte brut pour le NLP."""
    if not raw:
        return ""

    text = raw

    # 1. Supprime les placeholders {ap}, {dp}, {av}…
    text = _RE_PLACEHOLDERS.sub("", text)

    # 2. Décode les entités HTML
    text = html.unescape(text)

    # 3. Supprime les balises HTML résiduelles
    text = _RE_HTML_TAGS.sub(" ", text)

    # 4. Supprime les entités HTML restantes
    text = _RE_HTML_ENTITIES.sub(" ", text)

    # 5. Supprime les URLs inline
    text = _RE_INLINE_URLS.sub("", text)

    # 6. Supprime les caractères de contrôle
    text = _RE_CTRL_CHARS.sub("", text)

    # 7. Filtre les lignes de bruit
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            lines.append("")
            continue
        if _NOISE_PATTERNS.search(line):
            continue
        if _RE_COUNTRY_LINE.match(line):
            continue
        if len(line) < 4:
            continue
        lines.append(line)
    text = "\n".join(lines)

    # 8. Supprime les caractères spéciaux répétés
    text = _RE_REPEATED_CHARS.sub(r"\1", text)

    # 9. Normalise les espaces et sauts de ligne
    text = _RE_MULTI_NEWLINE.sub("\n\n", text)
    text = _RE_MULTI_SPACE.sub(" ", text)

    return text.strip()


# ─────────────────────────────────────────────
#  NORMALISATION DE LA DATE
# ─────────────────────────────────────────────

def normalize_date(raw_date: str) -> str:
    """
    Normalise n'importe quel format de date vers YYYY-MM-DD.
    Retourne "" si absente ou non parseable.
    """
    if not raw_date or not str(raw_date).strip():
        return ""
    try:
        parsed = dateparser.parse(str(raw_date), fuzzy=True)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────
#  DÉTECTION DE LANGUE
# ─────────────────────────────────────────────

_FR = [" le ", " la ", " les ", " de ", " des ", " et ", " pour ",
       " avec ", " une ", " un ", " est ", " nous ", " vous ", " ils "]
_EN = [" the ", " and ", " for ", " with ", " of ", " in ", " on ",
       " is ", " are ", " was ", " that ", " this ", " have ", " has "]


def detect_language_reliable(text: str, declared: str = "") -> str:
    if not text or len(text) < 50:
        return declared if declared in ("fr", "en") else "unknown"
    sample  = f" {text[:2000].lower()} "
    fr_score = sum(w in sample for w in _FR)
    en_score = sum(w in sample for w in _EN)
    if fr_score == 0 and en_score == 0:
        return declared if declared in ("fr", "en") else "unknown"
    return "fr" if fr_score >= en_score else "en"


# ─────────────────────────────────────────────
#  VALIDATION URL
# ─────────────────────────────────────────────

def validate_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(str(url).strip())
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────
#  NETTOYAGE D'UN ARTICLE
# ─────────────────────────────────────────────

def clean_article(article: dict, company_name: str = "") -> dict:
    """
    Nettoie un article et retourne un dict avec UNIQUEMENT les champs KEEP_FIELDS.
    """
    # ── Champs nettoyés
    url   = validate_url(article.get("url", ""))

    raw_date = article.get("date_publication") or article.get("date_rss") or ""
    date  = normalize_date(raw_date)

    raw_text = article.get("texte_complet") or article.get("extrait") or ""
    texte = clean_text_for_nlp(raw_text)

    langue = detect_language_reliable(
        texte, declared=article.get("langue", "")
    )

    titre  = _RE_PLACEHOLDERS.sub("", article.get("titre") or article.get("titre_rss") or "")
    titre  = re.sub(r"\s+", " ", titre).strip()

    extrait = _RE_PLACEHOLDERS.sub("", article.get("extrait") or "")
    extrait = clean_text_for_nlp(extrait)

    # ── Flags NLP
    missing   = [f for f in NLP_REQUIRED if not (
        url if f == "url" else
        date if f == "date_publication" else
        texte if f == "texte_complet" else
        langue if f == "langue" else ""
    )]
    text_ok   = len(texte) >= MIN_TEXT_LENGTH
    nlp_ready = len(missing) == 0 and text_ok

    # ── Retourne UNIQUEMENT les champs voulus
    return {
        "company_name":     company_name,
        "titre":            titre,
        "url":              url,
        "source":           article.get("source", ""),
        "date_publication": date,
        "langue":           langue,
        "auteur":           article.get("auteur", ""),
        "extrait":          extrait,
        "texte_complet":    texte,
        "nlp_ready":        nlp_ready,
        "nlp_missing":      missing,
        "nlp_text_length":  len(texte),
    }


# ─────────────────────────────────────────────
#  SAUVEGARDE
# ─────────────────────────────────────────────

def _flatten(value) -> str:
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value) if value is not None else ""


def save_json(articles: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=4)
    print(f"[OK] JSON → {path}")


def save_csv(articles: list, path: str):
    if not articles:
        print("[WARN] Aucun article à écrire dans le CSV.")
        return
    rows = [{k: _flatten(v) for k, v in a.items()} for a in articles]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=KEEP_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] CSV  → {path}")


# ─────────────────────────────────────────────
#  PIPELINE
# ─────────────────────────────────────────────

def run_cleaning_pipeline(
    input_path:   str = INPUT_JSON,
    output_json:  str = OUTPUT_JSON,
    output_csv:   str = OUTPUT_CSV,
    company_name: str = "",
) -> list:

    print(f"[LOAD] Lecture de {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        raw_articles = json.load(f)
    print(f"[LOAD] {len(raw_articles)} article(s) chargé(s)\n")

    cleaned_articles = []
    nlp_ready_count  = 0

    for idx, article in enumerate(raw_articles, 1):
        cleaned = clean_article(article, company_name=company_name)
        cleaned_articles.append(cleaned)

        status = "✓ NLP-ready" if cleaned["nlp_ready"] else f"⚠ manque : {cleaned['nlp_missing']}"
        print(f"  [{idx}/{len(raw_articles)}] {cleaned['url'][:65]}")
        print(f"      langue={cleaned['langue']}  "
              f"date={cleaned['date_publication'] or '—'}  "
              f"texte={cleaned['nlp_text_length']} chars  {status}")

        if cleaned["nlp_ready"]:
            nlp_ready_count += 1

    print(f"\n{'─' * 55}")
    print(f"[RÉSUMÉ] {len(cleaned_articles)} article(s) nettoyé(s)")
    print(f"         {nlp_ready_count} prêts pour NLP")
    print(f"         {len(cleaned_articles) - nlp_ready_count} incomplets (gardés)")
    print(f"{'─' * 55}\n")

    # ── Accumulation : charge le JSON existant (structure par entreprise)
    companies_data = {}
    if os.path.exists(output_json):
        try:
            with open(output_json, "r", encoding="utf-8") as f:
                existing_list = json.load(f)
            # Reconstruit le dict depuis la structure groupée
            for company_block in existing_list:
                cname = company_block.get("company_name", "")
                if cname:
                    companies_data[cname] = {
                        "company_name": cname,
                        "articles": company_block.get("articles", [])
                    }
        except Exception:
            companies_data = {}

    # Ajoute les nouveaux articles dans le bon groupe
    seen_urls = set()
    # Collecte toutes les URLs déjà présentes
    for block in companies_data.values():
        for a in block["articles"]:
            seen_urls.add(a.get("url", "").strip())

    new_count = 0
    for article in cleaned_articles:
        url   = article.get("url", "").strip()
        cname = article.get("company_name", "Inconnu")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        # Retire company_name des champs de l'article (il est dans le parent)
        article_data = {k: v for k, v in article.items() if k != "company_name"}
        if cname not in companies_data:
            companies_data[cname] = {"company_name": cname, "articles": []}
        companies_data[cname]["articles"].append(article_data)
        new_count += 1

    # Convertit en liste ordonnée
    merged = list(companies_data.values())
    total  = sum(len(b["articles"]) for b in merged)

    print(f"[MERGE] +{new_count} article(s) → {len(merged)} entreprise(s), {total} article(s) au total")

    # Sauvegarde JSON groupé par entreprise
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=4)
    print(f"[OK] JSON → {output_json}")

    # Sauvegarde CSV à plat (avec company_name)
    flat_rows = []
    for block in merged:
        cname = block["company_name"]
        for a in block["articles"]:
            row = {"company_name": cname}
            row.update(a)
            flat_rows.append({k: _flatten(v) for k, v in row.items()})
    if flat_rows:
        fieldnames = ["company_name"] + [k for k in flat_rows[0].keys() if k != "company_name"]
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat_rows)
        print(f"[OK] CSV  → {output_csv}")

    return merged


# ─────────────────────────────────────────────
#  POINT D'ENTRÉE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    run_cleaning_pipeline()