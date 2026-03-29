"""
pipeline.py — Point d'entrée unique du système Sales Intelligence

Usage :
    # URL unique
    python pipeline.py --url https://confoline.com

    # Batch (fichier texte avec 1 URL par ligne)
    python pipeline.py --batch urls.txt

    # Resume (reprend où ça s'est arrêté)
    python pipeline.py --batch urls.txt --resume
"""

import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from config import (
    OUTPUT_MD, OUTPUT_JSON, OUTPUT_FINAL,
    LOGS_DIR, PROGRESS_FILE,
    STOP_ON_ERROR, SAVE_PARTIAL_RESULTS
)

from acquisition.scraper1 import run as scraper1_run
from acquisition.scraper2 import run as scraper2_run
from extraction.md_to_json import process_markdown
from extraction.clean_secondary import process_secondary_pages


# ── Setup logging ─────────────────────────────────────────────
def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8")
        ]
    )
    return logging.getLogger(__name__)


# ── Progress management ───────────────────────────────────────
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

def reset_progress():
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()


# ── Pipeline pour une entreprise ─────────────────────────────
async def process_company(url: str, logger) -> dict | None:
    """
    Pipeline complet pour une URL :
    1. Scrapper 1 → .md
    2. md_to_json → JSON v1
    3. Scrapper 2 → secondary_pages
    4. clean_secondary → secondary_data
    """

    logger.info(f"\n{'='*60}")
    logger.info(f"🏢 Traitement : {url}")
    logger.info(f"{'='*60}")

    # ── PHASE 1 : Scrapper 1 ──────────────────────────────────
    logger.info(f"\n📡 PHASE 1 — Scrapper 1")
    try:
        result1 = await scraper1_run(url)
        if not result1:
            raise Exception("Scrapper 1 n'a rien retourné")
        md_path, scrape_method = result1
        logger.info(f"  ✅ .md sauvegardé : {md_path} (méthode: {scrape_method})")
    except Exception as e:
        logger.error(f"  ❌ PHASE 1 échouée : {e}")
        return None

    # ── PHASE 2 : md_to_json ──────────────────────────────────
    logger.info(f"\n🔍 PHASE 2 — Extraction regex + welcome_data")
    try:
        company = process_markdown(md_path)
        company["scrape_method"] = scrape_method
        logger.info(f"  ✅ JSON v1 généré")
        _save_json(company, "v1", url)
    except Exception as e:
        logger.error(f"  ❌ PHASE 2 échouée : {e}")
        return None

    # ── PHASE 3 : Scrapper 2 ─────────────────────────────────
    logger.info(f"\n📡 PHASE 3 — Scrapper 2 (méthode héritée: {scrape_method})")
    try:
        company = await scraper2_run(company, scrape_method)
        logger.info(f"  ✅ secondary_pages ajoutées")
        _save_json(company, "v2", url)
    except Exception as e:
        logger.error(f"  ❌ PHASE 3 échouée : {e}")
        if SAVE_PARTIAL_RESULTS:
            _save_json(company, "partial", url)
        return None

    # ── PHASE 4 : Clean secondary ─────────────────────────────
    logger.info(f"\n🧹 PHASE 4 — Nettoyage pages internes")
    try:
        company = process_secondary_pages(company)
        logger.info(f"  ✅ secondary_data généré")
        _save_json(company, "v3", url)
    except Exception as e:
        logger.error(f"  ❌ PHASE 4 échouée : {e}")
        if SAVE_PARTIAL_RESULTS:
            _save_json(company, "partial", url)
        return None

    return company


def _save_json(data: dict, version: str, url: str):
    OUTPUT_JSON.mkdir(parents=True, exist_ok=True)
    slug = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_")
    path = OUTPUT_JSON / f"{slug}_{version}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _save_final(dataset: list):
    OUTPUT_FINAL.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_FINAL / f"sales_intelligence_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=4, ensure_ascii=False)
    return path


# ── Main ─────────────────────────────────────────────────────
async def main():
    logger = setup_logging()
    parser = argparse.ArgumentParser(description="Sales Intelligence Pipeline")
    parser.add_argument("--url",    type=str, help="URL unique à traiter")
    parser.add_argument("--batch",  type=str, help="Fichier texte avec URLs (1 par ligne)")
    parser.add_argument("--resume", action="store_true", help="Reprendre où on s'est arrêté")
    args = parser.parse_args()

    if not args.url and not args.batch:
        print("❌ Spécifie --url ou --batch")
        sys.exit(1)

    if args.url:
        urls = [args.url.strip()]
    else:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"❌ Fichier introuvable : {args.batch}")
            sys.exit(1)
        urls = [l.strip() for l in batch_file.read_text(encoding="utf-8-sig").splitlines() if l.strip() and not l.strip().startswith("#")]

    progress = load_progress() if args.resume else {}
    if not args.resume:
        reset_progress()

    logger.info(f"🚀 Pipeline démarré — {len(urls)} URL(s)")

    dataset = []
    stats   = {"success": 0, "failed": 0, "skipped": 0}

    for i, url in enumerate(urls, 1):
        logger.info(f"\n[{i}/{len(urls)}] {url}")

        if args.resume and progress.get(url) == "done":
            logger.info(f"  ⏭️  Déjà traité (resume) — skip")
            stats["skipped"] += 1
            continue

        try:
            company = await process_company(url, logger)

            if company:
                dataset.append(company)
                progress[url] = "done"
                stats["success"] += 1
                logger.info(f"  ✅ {url} → terminé")
            else:
                progress[url] = "failed"
                stats["failed"] += 1
                logger.error(f"  ❌ {url} → échoué")

                if STOP_ON_ERROR:
                    logger.error(f"\n🛑 STOP_ON_ERROR=True → arrêt du pipeline")
                    save_progress(progress)
                    if dataset:
                        path = _save_final(dataset)
                        logger.info(f"💾 Résultat partiel sauvegardé : {path}")
                    break

        except Exception as e:
            progress[url] = "failed"
            stats["failed"] += 1
            logger.error(f"  ❌ Exception inattendue sur {url} : {e}")

            if STOP_ON_ERROR:
                logger.error(f"\n🛑 STOP_ON_ERROR=True → arrêt du pipeline")
                save_progress(progress)
                if dataset:
                    path = _save_final(dataset)
                    logger.info(f"💾 Résultat partiel sauvegardé : {path}")
                break

        save_progress(progress)

    if dataset:
        path = _save_final(dataset)
        logger.info(f"\n💾 Dataset final : {path}")

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Pipeline terminé")
    logger.info(f"📊 Succès  : {stats['success']}")
    logger.info(f"❌ Échecs  : {stats['failed']}")
    logger.info(f"⏭️  Skipped : {stats['skipped']}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())