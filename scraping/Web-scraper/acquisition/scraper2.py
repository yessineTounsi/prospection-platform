"""
scraper2.py — Scrape les URLs internes en héritant la méthode de scraper1
"""
import asyncio
import logging
import random

from acquisition.dns_checker import domain_exists
from acquisition.crawler import crawl_site
from acquisition.evaluator import evaluate_and_prepare
from acquisition.flaresolverr import scrape_with_flaresolverr
from acquisition.html_to_md import html_to_markdown
from config import DELAY_BETWEEN_URLS_MIN, DELAY_BETWEEN_URLS_MAX

logger = logging.getLogger(__name__)


async def _scrape_with_crawl4ai(url: str) -> str | None:
    """Scrape une URL avec crawl4ai + evaluate_and_prepare."""
    logger.info(f"    🔍 Crawl4AI : {url}")
    markdown = await crawl_site(url)
    if not markdown:
        logger.warning(f"    ❌ Crawl4AI n'a rien retourné")
        return None

    result = evaluate_and_prepare(markdown)
    if result["action"] == "process":
        logger.info(f"    ✅ Contenu valide ({result['status']})")
        return result["content"]

    logger.warning(f"    ⚠️  Contenu invalide ({result['status']})")
    return None


async def _scrape_with_flaresolverr(url: str) -> str | None:
    """Scrape une URL directement avec FlareSolverr."""
    logger.info(f"    🔥 FlareSolverr : {url}")
    html = scrape_with_flaresolverr(url)
    if not html:
        logger.error(f"    ❌ FlareSolverr échoué")
        return None

    markdown = html_to_markdown(html)
    if not markdown:
        return None

    result = evaluate_and_prepare(markdown)
    if result["action"] == "process":
        logger.info(f"    ✅ Contenu valide ({result['status']})")
        return result["content"]

    logger.warning(f"    ⚠️  Contenu invalide après FlareSolverr ({result['status']})")
    return None


async def _scrape_url(url: str, method: str) -> str | None:
    """
    Scrape une URL interne en utilisant la méthode héritée de scraper1.
    - method="crawl4ai"    → crawl4ai uniquement
    - method="flaresolverr" → FlareSolverr directement
    """
    if not domain_exists(url):
        logger.warning(f"    ❌ Domaine inexistant : {url}")
        return None

    if method == "flaresolverr":
        return await _scrape_with_flaresolverr(url)
    else:
        return await _scrape_with_crawl4ai(url)


async def run(company: dict, scrape_method: str = "crawl4ai") -> dict:
    """
    Scrape les internal_urls d'une entreprise.
    scrape_method : méthode héritée de scraper1 ("crawl4ai" ou "flaresolverr")
    """
    internal_urls = company.get("internal_urls", {})
    source        = company.get("source_file", "?")

    if not internal_urls:
        logger.info(f"  ⏭️  Pas d'URLs internes pour {source}")
        return company

    logger.info(f"  🏢 {source} — {len(internal_urls)} URLs internes — méthode: {scrape_method}")

    secondary_pages = {}

    for pattern, url in internal_urls.items():
        logger.info(f"  → [{pattern}] {url}")

        md = await _scrape_url(url, scrape_method)
        secondary_pages[pattern] = f"## {pattern.upper()}\n\n{md}" if md else "failed"

        delay = random.uniform(DELAY_BETWEEN_URLS_MIN, DELAY_BETWEEN_URLS_MAX)
        logger.info(f"    ⏱️  Pause {delay:.1f}s")
        await asyncio.sleep(delay)

    company["secondary_pages"] = secondary_pages
    company["scrape_method"]   = scrape_method

    # Enrichir raw_markdown
    successful = [v for v in secondary_pages.values() if v != "failed"]
    if successful:
        sep = "\n\n" + "─" * 50 + "\n\n"
        company["raw_markdown"] = company.get("raw_markdown", "") + sep + sep.join(successful)
        logger.info(f"  ✅ {len(successful)}/{len(internal_urls)} pages scrapées")
    else:
        logger.warning(f"  ⚠️  Aucune page secondaire récupérée")

    return company