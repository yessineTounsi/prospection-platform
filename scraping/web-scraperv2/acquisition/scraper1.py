"""
acquisition/scraper1.py — Scraping de la welcome page
======================================================
Responsabilites :
  1. Normaliser l URL d entree (ajouter https:// si absent)
  2. Verifier que le domaine existe (DNS check)
  3. Scraper avec Crawl4AI (headless browser)
  4. Fallback FlareSolverr si Cloudflare ou JS blocking detecte
  5. Sauvegarder le markdown brut dans output/md/

Retourne (md_path, methode) ou None si echec total.
"""

import logging
from pathlib import Path

from acquisition.dns_checker  import domain_exists
from acquisition.crawler      import crawl_site
from acquisition.evaluator    import is_content_valid
from acquisition.flaresolverr import scrape_with_flaresolverr
from acquisition.html_to_md   import html_to_markdown
from config                   import OUTPUT_MD

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """
    Normalise l URL d entree.
    Ajoute https:// si le schema est absent.
    Ex: 'confoline.com' → 'https://confoline.com'
    """
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


def _url_to_filename(url: str) -> str:
    """Convertit une URL en nom de fichier .md valide."""
    return (
        url.replace("https://", "")
           .replace("http://", "")
           .replace("/", "_")
           .replace(".", "_")
        + ".md"
    )


async def scrape_welcome_page(url: str) -> dict | None:
    """
    Scrape la welcome page d un site.

    Strategie :
      1. Crawl4AI (rapide, headless Chromium)
      2. FlareSolverr si Crawl4AI retourne contenu invalide
         (bot protection, JS blocking, Cloudflare...)

    Returns:
        {"markdown": str, "method": "crawl4ai" | "flaresolverr"} ou None
    """
    if not domain_exists(url):
        logger.warning("  Domaine inexistant : " + url)
        return None

    # Tentative principale — Crawl4AI
    logger.info("  Crawl4AI : " + url)
    markdown = await crawl_site(url)

    if markdown and is_content_valid(markdown):
        logger.info("  Contenu valide (crawl4ai)")
        return {"markdown": markdown, "method": "crawl4ai"}

    # Fallback — FlareSolverr (anti-bot)
    logger.warning("  Crawl4AI insuffisant → FlareSolverr")
    html = scrape_with_flaresolverr(url)
    if not html:
        logger.error("  FlareSolverr echoue : " + url)
        return None

    markdown = html_to_markdown(html)
    if markdown and is_content_valid(markdown):
        logger.info("  Contenu valide (flaresolverr)")
        return {"markdown": markdown, "method": "flaresolverr"}

    logger.error("  Contenu invalide meme apres FlareSolverr")
    return None


def save_markdown(url: str, markdown: str) -> Path:
    """Sauvegarde le markdown brut dans output/md/."""
    OUTPUT_MD.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_MD / _url_to_filename(url)
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    logger.info("  Sauvegarde : " + str(path))
    return path


async def run(url: str) -> tuple | None:
    """
    Point d entree principal du scraper 1.

    Args:
        url : URL du site (avec ou sans https://)

    Returns:
        (md_path: Path, method: str) ou None si echec
    """
    # Normaliser l URL avant tout traitement
    url = _normalize_url(url)

    logger.info("Scrapper 1 → " + url)
    result = await scrape_welcome_page(url)
    if not result:
        return None

    md_path = save_markdown(url, result["markdown"])
    return md_path, result["method"]