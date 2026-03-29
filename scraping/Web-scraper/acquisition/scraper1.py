"""
scraper1.py — Scrape la welcome page et retourne markdown + méthode utilisée
"""
import asyncio
import logging
from pathlib import Path

from acquisition.dns_checker import domain_exists
from acquisition.crawler import crawl_site
from acquisition.evaluator import is_content_valid
from acquisition.flaresolverr import scrape_with_flaresolverr
from acquisition.html_to_md import html_to_markdown
from config import OUTPUT_MD

logger = logging.getLogger(__name__)


def _url_to_filename(url: str) -> str:
    return (
        url.replace("https://", "")
           .replace("http://", "")
           .replace("/", "_")
           .replace(".", "_")
        + ".md"
    )


async def scrape_welcome_page(url: str) -> dict | None:
    """
    Scrape la welcome page.
    Retourne {"markdown": str, "method": "crawl4ai" | "flaresolverr"}
    ou None si échec total.
    """
    if not domain_exists(url):
        logger.warning(f"  ❌ Domaine inexistant : {url}")
        return None

    # Tentative crawl4ai (1 seule)
    logger.info(f"  🔍 Crawl4AI : {url}")
    markdown = await crawl_site(url)

    if markdown and is_content_valid(markdown):
        logger.info(f"  ✅ Contenu valide (crawl4ai)")
        return {"markdown": markdown, "method": "crawl4ai"}

    # Fallback FlareSolverr
    logger.warning(f"  ⚠️  crawl4ai insuffisant → FlareSolverr")
    html = scrape_with_flaresolverr(url)
    if not html:
        logger.error(f"  ❌ FlareSolverr échoué : {url}")
        return None

    markdown = html_to_markdown(html)
    if markdown and is_content_valid(markdown):
        logger.info(f"  ✅ Contenu valide (flaresolverr)")
        return {"markdown": markdown, "method": "flaresolverr"}

    logger.error(f"  ❌ Contenu invalide même après FlareSolverr")
    return None


def save_markdown(url: str, markdown: str) -> Path:
    OUTPUT_MD.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_MD / _url_to_filename(url)
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown)
    logger.info(f"  📄 Sauvegardé : {path}")
    return path


async def run(url: str) -> tuple[Path, str] | None:
    """
    Point d'entrée scrapper 1.
    Retourne (md_path, method) ou None si échec.
    """
    logger.info(f"\n🌐 Scrapper 1 → {url}")
    result = await scrape_welcome_page(url)
    if not result:
        return None
    md_path = save_markdown(url, result["markdown"])
    return md_path, result["method"]