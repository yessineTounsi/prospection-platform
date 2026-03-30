"""
router.py — Routeur finance
Règles :
  1. country == France → Pappers en premier
       - score OK  → retourne raw Pappers
       - score NOK → fallback Yahoo si FALLBACK_YAHOO_IF_PAPPERS_FAILS
  2. country != France → Yahoo directement
       - score OK  → retourne raw Yahoo
       - score NOK → finance_data = None
  3. country = None → Yahoo si TRY_YAHOO_IF_NO_COUNTRY
"""

import logging

logger = logging.getLogger(__name__)

# ── Config inline (pas de fichier config externe) ─────────────
MIN_SCORE_PAPPERS               = 0.50
MIN_SCORE_YAHOO                 = 0.35
FALLBACK_YAHOO_IF_PAPPERS_FAILS = True
TRY_YAHOO_IF_NO_COUNTRY         = True
FRANCE_VARIANTS = {
    "france", "fr", "french", "française",
    "francaise", "france metropolitaine"
}


def _normalize_country(raw: str | None) -> str:
    return (raw or "").strip().lower()


async def enrich(company: dict) -> dict:
    """Point d'entrée unique. Retourne toujours company."""
    from sources.pappersfr import fetch as pappers_fetch
    from sources.yahoo      import fetch as yahoo_fetch

    country = _normalize_country(company.get("country"))
    name    = company.get("company_name") or ""
    website = company.get("website_url")  or ""
    address = company.get("address")      or ""

    logger.info(f"[Router] country={country!r} | name={name!r} | url={website!r}")

    if not name and not website:
        logger.warning("[Router] Aucune clé de jointure — finance ignorée")
        return _set_result(company, None, "no_keys", None)

    if country in FRANCE_VARIANTS:
        return await _route_france(company, name, address, website, pappers_fetch, yahoo_fetch)

    if country or TRY_YAHOO_IF_NO_COUNTRY:
        return await _route_international(company, website, name, country, address, yahoo_fetch)

    return _set_result(company, None, "no_country", None)


async def _route_france(company, name, address, website, pappers_fetch, yahoo_fetch):
    logger.info("[Router] Route → Pappers")
    result = await pappers_fetch(name, address)

    if result and result.get("_confidence", 0) >= MIN_SCORE_PAPPERS:
        logger.info(f"[Pappers] Match OK — confidence={result['_confidence']:.2f}")
        return _set_result(company, result, "pappers", result["_confidence"])

    logger.warning("[Pappers] Score insuffisant ou aucun résultat")

    if FALLBACK_YAHOO_IF_PAPPERS_FAILS:
        logger.info("[Router] Fallback → Yahoo")
        return await _route_international(
            company, website, name, "france", address,
            yahoo_fetch, source_prefix="pappers_fallback_"
        )

    return _set_result(company, None, "pappers_no_match", None)


async def _route_international(company, website, name, country, address,
                                yahoo_fetch, source_prefix=""):
    logger.info("[Router] Route → Yahoo Finance")
    result = yahoo_fetch(website, name, country, address)

    if result and result.get("_match_score", 0) >= MIN_SCORE_YAHOO:
        logger.info(f"[Yahoo] Match OK — score={result['_match_score']:.2f}")
        return _set_result(company, result, f"{source_prefix}yahoo", result["_match_score"])

    logger.warning("[Yahoo] Score insuffisant ou aucun résultat")
    return _set_result(company, None, f"{source_prefix}yahoo_no_match", None)


def _set_result(company, data, source, confidence):
    company["finance_data"]       = data
    company["finance_source"]     = source
    company["finance_confidence"] = confidence
    return company