import trafilatura
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, UTC

from fetcher import fetch_page, fetch_page_dynamic
from utils import clean_text, extract_meta, detect_language
from classifier import detect_article_type, classify_subject


# ─────────────────────────────────────────────
#  DÉTECTION DE PAGE ARTICLE
# ─────────────────────────────────────────────

def is_article_page(html: str, url: str) -> bool:
    """
    Détermine si une page HTML est un article (vs listing, about, etc.).
    Critères : texte extrait suffisant, balise date, tag <article>, ou titre long.
    """
    soup           = BeautifulSoup(html, "html.parser")
    extracted_text = trafilatura.extract(html) or ""

    if len(extracted_text) > 300:
        return True

    date_metas = [
        ("property", "article:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
        ("name", "publish-date"),
    ]
    for attr_name, attr_value in date_metas:
        if extract_meta(soup, attr_name, attr_value):
            return True

    if soup.find("article"):
        return True

    page_title = clean_text(soup.title.get_text()) if soup.title else ""
    if page_title and len(page_title) > 20:
        return True

    return False


# ─────────────────────────────────────────────
#  EXTRACTION DU CONTENU D'UN ARTICLE
# ─────────────────────────────────────────────

def extract_article_content(article_url: str) -> dict:
    """
    Extrait toutes les métadonnées et le texte complet d'un article.
    Utilise trafilatura pour le texte, BeautifulSoup pour les métadonnées.
    Fallback Playwright si le texte est insuffisant (site JS).

    Retourne un dictionnaire prêt à être stocké.
    """
    # ── Fetch initial
    try:
        html = fetch_page(article_url)
    except Exception:
        html = fetch_page_dynamic(article_url)

    soup           = BeautifulSoup(html, "html.parser")
    extracted_text = trafilatura.extract(html) or ""

    # ── Fallback Playwright si texte insuffisant
    if len(extracted_text) < 100:
        try:
            html           = fetch_page_dynamic(article_url)
            extracted_text = trafilatura.extract(html) or extracted_text
            soup           = BeautifulSoup(html, "html.parser")
        except Exception:
            pass

    # ── Titre
    title    = clean_text(soup.title.get_text()) if soup.title else ""
    og_title = extract_meta(soup, "property", "og:title")
    if og_title:
        title = og_title

    # ── Auteur
    author = (
        extract_meta(soup, "name", "author") or
        extract_meta(soup, "property", "article:author")
    )

    # ── Date de publication
    date_publication = ""
    for attr_name, attr_value in [
        ("property", "article:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
        ("name", "publish-date"),
    ]:
        value = extract_meta(soup, attr_name, attr_value)
        if value:
            date_publication = value
            break

    # ── Description / extrait
    description = (
        extract_meta(soup, "name", "description") or
        extract_meta(soup, "property", "og:description")
    )
    if not description:
        description = extracted_text[:300] + "..." if len(extracted_text) > 300 else extracted_text

    # ── Mots-clés
    keywords_raw = extract_meta(soup, "name", "keywords")
    keywords     = [k.strip() for k in keywords_raw.split(",") if k.strip()] if keywords_raw else []

    # ── Enrichissement
    language     = detect_language(extracted_text or title)
    source       = urlparse(article_url).netloc.replace("www.", "")
    categories   = classify_subject(extracted_text)
    article_type = detect_article_type(extracted_text)

    return {
        "titre":               title,
        "source":              source,
        "date_publication":    date_publication,
        "url":                 article_url,
        "langue":              language,
        "auteur":              author,
        "extrait":             description,
        "texte_complet":       extracted_text,
        "mots_cles":           keywords,
        "categories_detectees":categories,
        "article_type":        article_type,
        "date_scraping":       datetime.now(UTC).isoformat(),
    }