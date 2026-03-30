"""
sources/yahoo.py — Wrapper Yahoo Finance pour le router
Retourne raw dict tel que retourné par find_ticker() + _source
"""
import logging

logger = logging.getLogger(__name__)


def fetch(website_url: str, company_name: str = "",
          country: str = "", address: str = "") -> dict | None:
    """
    Appelle find_ticker(), retourne raw dict Yahoo.
    Retourne None si aucun match.
    """
    try:
        from yahoo_api import find_ticker

        result = find_ticker(
            website_url=website_url,
            company_name=company_name,
            country=country,
            address=address,
        )

        if not result:
            logger.warning(f"[Yahoo] Aucun match pour {website_url!r}")
            return None

        result["_source"] = "yahoo"
        logger.info(
            f"[Yahoo] {result.get('symbol')} — "
            f"score={result.get('_match_score', 0):.2f} "
            f"({result.get('_match_method')})"
        )
        return result

    except Exception as e:
        logger.error(f"[Yahoo] Exception pour {website_url!r} : {e}")
        return None