"""
acquisition/scraper2.py — Scraping des pages internes selectionnees
====================================================================
Scrape les URLs identifiees par le link scorer (about, team, services...).
Herite la methode de scraping de scraper1 (crawl4ai ou flaresolverr).

Flux :
    company["internal_urls"] → scraper2 → company["secondary_pages"]
    {about: url, team: url}  →           {about: markdown, team: markdown}
"""

import asyncio
import logging
import random

from acquisition.dns_checker  import domain_exists
from acquisition.crawler      import crawl_site
from acquisition.evaluator    import evaluate_and_prepare
from acquisition.flaresolverr import scrape_with_flaresolverr
from acquisition.html_to_md   import html_to_markdown
from config import DELAY_BETWEEN_URLS_MIN, DELAY_BETWEEN_URLS_MAX

logger = logging.getLogger(__name__)


async def _scrape_with_crawl4ai(url: str) -> str | None:
    """
    Scrape une URL interne avec Crawl4AI.
    Passe le contenu par evaluate_and_prepare pour filtrer
    les pages bloquees, les dumps de navigation, les pages legales.
    """
    logger.info("    Crawl4AI : " + url)
    markdown = await crawl_site(url)
    if not markdown:
        logger.warning("    Crawl4AI : rien retourne")
        return None

    result = evaluate_and_prepare(markdown)
    if result["action"] == "process":
        logger.info("    Contenu valide (" + result["status"] + ")")
        return result["content"]

    logger.warning("    Contenu invalide (" + result["status"] + ")")
    return None


async def _scrape_with_flaresolverr(url: str) -> str | None:
    """
    Scrape une URL interne avec FlareSolverr.
    Utilise quand le site entier necessite le contournement anti-bot.
    """
    logger.info("    FlareSolverr : " + url)
    html = scrape_with_flaresolverr(url)
    if not html:
        logger.error("    FlareSolverr echoue")
        return None

    markdown = html_to_markdown(html)
    if not markdown:
        return None

    result = evaluate_and_prepare(markdown)
    if result["action"] == "process":
        logger.info("    Contenu valide (" + result["status"] + ")")
        return result["content"]

    logger.warning("    Contenu invalide apres FlareSolverr (" + result["status"] + ")")
    return None


async def _scrape_url(url: str, method: str) -> str | None:
    """
    Scrape une URL interne en utilisant la methode heritee de scraper1.

    Args:
        url    : URL a scraper
        method : "crawl4ai" ou "flaresolverr" (herite de scraper1)

    Returns:
        Markdown brut ou None si echec
    """
    if not domain_exists(url):
        logger.warning("    Domaine inexistant : " + url)
        return None

    if method == "flaresolverr":
        return await _scrape_with_flaresolverr(url)
    else:
        return await _scrape_with_crawl4ai(url)


async def run(company: dict, scrape_method: str = "crawl4ai") -> dict:
    """
    Scrape toutes les pages internes d une entreprise.

    Args:
        company       : Dict entreprise avec internal_urls rempli par le scorer
        scrape_method : Methode heritee de scraper1 ("crawl4ai" ou "flaresolverr")

    Returns:
        company enrichi avec :
          - secondary_pages : {categorie: markdown_brut | "failed"}
          - raw_markdown    : Concatenation welcome + pages internes
    """
    internal_urls = company.get("internal_urls", {})
    source        = company.get("source_file", "?")

    if not internal_urls:
        logger.info("  Pas de pages internes pour " + source)
        return company

    logger.info("  " + source + " — " + str(len(internal_urls)) +
                " pages internes — methode: " + scrape_method)

    secondary_pages = {}

    for category, url in internal_urls.items():
        logger.info("  [" + category + "] " + url)

        md = await _scrape_url(url, scrape_method)

        # Prefixer le markdown avec le nom de categorie (facilite le nettoyage)
        secondary_pages[category] = (
            "## " + category.upper() + "\n\n" + md
            if md else "failed"
        )

        # Pause anti-ban entre chaque page
        delay = random.uniform(DELAY_BETWEEN_URLS_MIN, DELAY_BETWEEN_URLS_MAX)
        logger.info("    Pause " + f"{delay:.1f}s")
        await asyncio.sleep(delay)

    company["secondary_pages"] = secondary_pages
    company["scrape_method"]   = scrape_method

    # Enrichir raw_markdown avec le contenu des pages internes
    # (utilise par le scorer sur les pages secondaires si necessaire)
    successful = [v for v in secondary_pages.values() if v != "failed"]
    if successful:
        sep = "\n\n" + "─" * 50 + "\n\n"
        company["raw_markdown"] = (
            company.get("raw_markdown", "") + sep + sep.join(successful)
        )
        logger.info("  " + str(len(successful)) + "/" +
                    str(len(internal_urls)) + " pages scrapees")
    else:
        logger.warning("  Aucune page secondaire recuperee")

    return company