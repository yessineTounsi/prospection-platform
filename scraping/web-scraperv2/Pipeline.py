"""
Pipeline.py — Point d entree unique du systeme Sales Intelligence
=================================================================
Orchestre les 4 phases du pipeline de collecte web :

  PHASE 1 : Scraper1     → Welcome page → Markdown brut
  PHASE 2 : md_to_json   → Extraction regex (email, phone, linkedin, pays...)
  PHASE 3 : Link Scorer  → Selection semantique des pages internes
  PHASE 4 : Scraper2     → Scraping des pages selectionnees
  PHASE 5 : Nettoyage    → Clean text + paragraphes structures

Usage :
    # URL unique
    python Pipeline.py --url https://www.biat.com.tn

    # Batch (fichier texte, 1 URL par ligne, # pour commenter)
    python Pipeline.py --batch urls.txt

    # Reprendre un batch interrompu
    python Pipeline.py --batch urls.txt --resume

Output :
    output/json/   → JSONs intermediaires (v1, v1_scored, v2, v3)
    output/final/  → Dataset final sales_intelligence_YYYYMMDD_HHMMSS.json
    logs/          → Logs detailles par execution
"""

import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from config import (
    OUTPUT_JSON, OUTPUT_FINAL, LOGS_DIR, PROGRESS_FILE,
    STOP_ON_ERROR, SAVE_PARTIAL_RESULTS,
    SCORER_TOP_K, SCORER_MAX_PER_CAT,
)

from acquisition.scraper1       import run as scraper1_run
from acquisition.scraper2       import run as scraper2_run
from extraction.md_to_json      import process_markdown
from extraction.clean_secondary import process_secondary_pages
from extraction.llm_extractor   import extract_null_fields
from extraction.nlp_enricher    import enrich_with_nlp
from navigation.link_extractor  import extract_links
from navigation.llm_scorer      import (
    LLMScorer,
    scored_links_to_dict,
    scored_links_to_rich_dict,
)


# ── Singleton scorer ───────────────────────────────────────────────────────────
_scorer = None

def get_scorer() -> LLMScorer:
    global _scorer
    if _scorer is None:
        _scorer = LLMScorer()
    return _scorer


# ── Logging ────────────────────────────────────────────────────────────────────
def setup_logging() -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = LOGS_DIR / f"pipeline_{ts}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ]
    )
    return logging.getLogger(__name__)


# ── Gestion de la progression (resume) ────────────────────────────────────────
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}

def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

def reset_progress():
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()


# ── Phase 3 : Link Scorer ──────────────────────────────────────────────────────
def apply_link_scorer(company: dict, logger: logging.Logger) -> dict:
    """
    Selectionne les pages internes les plus pertinentes par scoring semantique.

    Lit le raw_markdown de la welcome page, extrait les liens internes,
    les score par similarite avec les categories cibles (about, team, services...),
    et stocke les meilleurs dans company["internal_urls"] et company["scored_navigation"].

    Args:
        company : Dict entreprise avec raw_markdown et website_url
        logger  : Logger du pipeline

    Returns:
        company enrichi avec internal_urls et scored_navigation
    """
    raw_md   = company.get("raw_markdown", "")
    base_url = company.get("website_url")

    if not raw_md:
        logger.warning("  Pas de raw_markdown — link scorer ignore")
        return company

    # Extraire et filtrer les liens internes
    links = extract_links(raw_md, base_url=base_url)

    if not links:
        logger.warning("  Aucun lien interne trouve")
        return company

    # Scorer et selectionner les meilleurs liens
    scorer  = get_scorer()
    results = scorer.score_links(links, top_k=SCORER_TOP_K, max_per_cat=SCORER_MAX_PER_CAT, base_url=base_url)

    company["internal_urls"]     = scored_links_to_dict(results)
    company["scored_navigation"] = scored_links_to_rich_dict(results)

    logger.info("  " + str(len(results)) + " pages selectionnees :")
    for cat, d in company["scored_navigation"].items():
        logger.info("    [" + cat + "] score=" + str(d["score"]) + "  " + d["url"])

    return company


# ── Pipeline complet pour une entreprise ──────────────────────────────────────
async def process_company(url: str, logger: logging.Logger) -> dict | None:
    """
    Execute le pipeline complet pour une URL.

    Phases :
      1. Scraper1   → Welcome page → .md
      2. md_to_json → Regex extractions → JSON v1
      3. Scorer     → Selection pages internes → JSON v1_scored
      4. Scraper2   → Pages internes → JSON v2
      5. Clean      → Secondary data → JSON v3

    Returns:
        Dict entreprise enrichi ou None si echec
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("TRAITEMENT : " + url)
    logger.info("=" * 60)

    # ── PHASE 1 : Welcome page ─────────────────────────────────────────────────
    logger.info("PHASE 1 — Scraper1 (welcome page)")
    try:
        result1 = await scraper1_run(url)
        if not result1:
            raise Exception("Scraper1 n a rien retourne")
        md_path, scrape_method = result1
        logger.info("  OK : " + str(md_path))
    except Exception as e:
        logger.error("  ECHEC : " + str(e))
        return None

    # ── PHASE 2 : Extraction regex ─────────────────────────────────────────────
    logger.info("PHASE 2 — Extraction regex (email, phone, linkedin, pays...)")
    try:
        company = process_markdown(md_path)
        company["scrape_method"] = scrape_method

        # Forcer website_url depuis l URL d entree
        # Evite les sous-domaines parasites (newsroom., app., adroll...)
        input_base = "/".join(url.split("/")[:3])
        if not company.get("website_url") or company["website_url"] != input_base:
            logger.info("  Correction website_url : " +
                        str(company.get("website_url")) + " → " + input_base)
            company["website_url"] = input_base

        logger.info("  OK : website_url=" + str(company["website_url"]) +
                    " | email=" + str(company.get("email")) +
                    " | phone=" + str(company.get("phone")) +
                    " | linkedin=" + str(company.get("linkedin")))
        _save_json(company, "v1", url)
    except Exception as e:
        logger.error("  ECHEC : " + str(e))
        return None

    # ── PHASE 3 : Link Scorer ──────────────────────────────────────────────────
    logger.info("PHASE 3 — Link Scorer (selection semantique des pages internes)")
    try:
        company = apply_link_scorer(company, logger)
        _save_json(company, "v1_scored", url)
    except Exception as e:
        logger.error("  ECHEC : " + str(e))
        logger.warning("  Continuation sans link scorer")

    # ── PHASE 4 : Scraper2 ─────────────────────────────────────────────────────
    logger.info("PHASE 4 — Scraper2 (pages internes | methode: " + scrape_method + ")")
    try:
        company  = await scraper2_run(company, scrape_method)
        pages_ok = sum(
            1 for v in company.get("secondary_pages", {}).values()
            if v != "failed"
        )
        logger.info("  OK : " + str(pages_ok) + "/" +
                    str(len(company.get("internal_urls", {}))) + " pages scrapees")
        _save_json(company, "v2", url)
    except Exception as e:
        logger.error("  ECHEC : " + str(e))
        if SAVE_PARTIAL_RESULTS:
            _save_json(company, "partial", url)
        return None

    # ── PHASE 5 : Nettoyage ────────────────────────────────────────────────────
    logger.info("PHASE 5 — Nettoyage et structuration des pages internes")
    try:
        company = process_secondary_pages(company)
        _save_json(company, "v3", url)
        logger.info("  OK : secondary_data genere")
    except Exception as e:
        logger.error("  ECHEC : " + str(e))
        if SAVE_PARTIAL_RESULTS:
            _save_json(company, "partial", url)
        return None

    # ── PHASE 6 : Extraction LLM des champs nuls ──────────────────────────────
    logger.info("PHASE 6 — Extraction LLM (company_name, description, services...)")
    try:
        company = extract_null_fields(company)
        _save_json(company, "v4", url)
        logger.info("  OK : champs enrichis par LLM")
    except Exception as e:
        logger.error("  ECHEC Phase 6 : " + str(e))
        logger.warning("  Continuation sans extraction LLM")

    # ── PHASE 7 : Enrichissement NLP spaCy ────────────────────────────────────
    logger.info("PHASE 7 — Enrichissement NLP (spaCy : métriques, certifs, techs, lieux...)")
    try:
        company = enrich_with_nlp(company)
        _save_json(company, "v5", url)
        logger.info("  OK : enrichissement NLP terminé")
    except Exception as e:
        logger.error("  ECHEC Phase 7 : " + str(e))
        logger.warning("  Continuation sans enrichissement NLP")

    return company


# ── Sauvegarde JSON ────────────────────────────────────────────────────────────
def _save_json(data: dict, version: str, url: str):
    """Sauvegarde un JSON intermediaire dans output/json/."""
    OUTPUT_JSON.mkdir(parents=True, exist_ok=True)
    slug = (url.replace("https://", "").replace("http://", "")
               .replace("/", "_").replace(".", "_"))
    path = OUTPUT_JSON / f"{slug}_{version}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


_INTERNAL_FIELDS = {"raw_markdown", "secondary_pages"}

def _clean_for_final(company: dict) -> dict:
    """Supprime les champs internes volumineux du JSON final."""
    return {k: v for k, v in company.items() if k not in _INTERNAL_FIELDS}


def _save_final(dataset: list) -> Path:
    """Sauvegarde le dataset final dans output/final/ (sans champs internes)."""
    OUTPUT_FINAL.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_FINAL / f"sales_intelligence_{ts}.json"
    clean_dataset = [_clean_for_final(c) for c in dataset]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean_dataset, f, indent=4, ensure_ascii=False)
    return path


# ── Main ───────────────────────────────────────────────────────────────────────
async def main():
    logger = setup_logging()

    parser = argparse.ArgumentParser(
        description="Sales Intelligence Pipeline — Web Scraper"
    )
    parser.add_argument("--url",    type=str,
                        help="URL unique a traiter")
    parser.add_argument("--batch",  type=str,
                        help="Fichier texte avec URLs (1 par ligne, # pour commenter)")
    parser.add_argument("--resume", action="store_true",
                        help="Reprendre un batch interrompu")
    args = parser.parse_args()

    if not args.url and not args.batch:
        print("Usage : python Pipeline.py --url https://... | --batch urls.txt")
        sys.exit(1)

    # Charger les URLs
    if args.url:
        urls = [args.url.strip()]
    else:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print("Fichier introuvable : " + args.batch)
            sys.exit(1)
        urls = [
            line.strip()
            for line in batch_file.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    # Gestion du resume
    progress = load_progress() if args.resume else {}
    if not args.resume:
        reset_progress()

    # Initialiser le scorer LLM (vérifie la connexion Ollama)
    logger.info("Initialisation du scorer LLM (Ollama)...")
    get_scorer()
    logger.info("Scorer LLM pret — modele : " + __import__('config').OLLAMA_MODEL)
    logger.info("Pipeline demarre — " + str(len(urls)) + " URL(s)")

    dataset = []
    stats   = {"success": 0, "failed": 0, "skipped": 0}

    for i, url in enumerate(urls, 1):
        logger.info("[" + str(i) + "/" + str(len(urls)) + "] " + url)

        # Skip si deja traite (mode resume)
        if args.resume and progress.get(url) == "done":
            logger.info("  Deja traite — skip")
            stats["skipped"] += 1
            continue

        try:
            company = await process_company(url, logger)

            if company:
                dataset.append(company)
                progress[url] = "done"
                stats["success"] += 1
                logger.info("  SUCCES : " + url)
            else:
                progress[url] = "failed"
                stats["failed"] += 1
                logger.error("  ECHEC : " + url)

                if STOP_ON_ERROR:
                    save_progress(progress)
                    if dataset:
                        path = _save_final(dataset)
                        logger.info("Partiel sauvegarde : " + str(path))
                    break

        except Exception as e:
            progress[url] = "failed"
            stats["failed"] += 1
            logger.error("Exception sur " + url + " : " + str(e))

            if STOP_ON_ERROR:
                save_progress(progress)
                if dataset:
                    path = _save_final(dataset)
                    logger.info("Partiel sauvegarde : " + str(path))
                break

        save_progress(progress)

    # Sauvegarder le dataset final
    if dataset:
        path = _save_final(dataset)
        logger.info("Dataset final : " + str(path))

    # Bilan
    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE TERMINE")
    logger.info("Succes  : " + str(stats["success"]) + "/" + str(len(urls)))
    logger.info("Echecs  : " + str(stats["failed"]))
    logger.info("Skipped : " + str(stats["skipped"]))
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())