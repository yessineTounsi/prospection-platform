"""
sources/pappersfr.py — Wrapper Pappers pour le router
Retourne raw JSON + _confidence normalisé 0.0–1.0
"""
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


async def fetch(company_name: str, address: str = None) -> dict | None:
    """
    Lance scrape Pappers, retourne raw dict + _confidence.
    Retourne None si aucun résultat ou erreur.
    """
    try:
        from pappers_scraper import scrape_company

        raw_path = await scrape_company(
            company_name=company_name,
            address=address,
            max_results=3,
        )

        if not raw_path:
            logger.warning(f"[Pappers] Aucun fichier pour {company_name!r}")
            return None

        path = Path(raw_path)
        if not path.exists():
            logger.error(f"[Pappers] Fichier introuvable : {raw_path}")
            return None

        raw = json.loads(path.read_text(encoding="utf-8"))

        # Normaliser score Pappers (0–100) → (0.0–1.0)
        raw_score = raw.get("_meta", {}).get("match_score", 0)
        raw["_confidence"] = round(raw_score / 100, 4)
        raw["_source"]     = "pappers"

        logger.info(
            f"[Pappers] {company_name!r} → "
            f"score={raw_score}/100 confidence={raw['_confidence']:.2f}"
        )
        return raw

    except Exception as e:
        logger.error(f"[Pappers] Exception pour {company_name!r} : {e}")
        return None