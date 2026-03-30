"""
finance_runner.py — Runner autonome, complètement isolé du pipeline
À placer dans : sales_intelligence/finance_scraper/

Usage :
    python finance_runner.py                        # interactif
    python finance_runner.py --name "Capgemini" --country "France" --url "https://www.capgemini.com"
    python finance_runner.py --batch test_companies.json
"""

import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

OUTPUT_DIR = ROOT / "finance_test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(OUTPUT_DIR / "finance_runner.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)


async def run_one(entry: dict) -> dict:
    from router import enrich

    company = {
        "company_name":       entry.get("name") or entry.get("company_name"),
        "website_url":        entry.get("url")  or entry.get("website_url"),
        "country":            entry.get("country"),
        "address":            entry.get("address"),
        "finance_data":       None,
        "finance_source":     None,
        "finance_confidence": None,
    }

    logger.info(f"\n{'='*60}")
    logger.info(f"Entreprise : {company['company_name']}")
    logger.info(f"URL        : {company['website_url']}")
    logger.info(f"Pays       : {company['country']}")
    logger.info(f"{'='*60}")

    start   = datetime.now()
    company = await enrich(company)
    elapsed = round((datetime.now() - start).total_seconds(), 2)

    company["_meta"] = {"tested_at": datetime.now().isoformat(), "elapsed_s": elapsed, "input": entry}

    _print_result(company)
    _save_result(company)
    return company


def _print_result(company: dict):
    source     = company.get("finance_source", "—")
    confidence = company.get("finance_confidence")
    data       = company.get("finance_data") or {}
    elapsed    = company.get("_meta", {}).get("elapsed_s", "?")

    print(f"\n{'─'*60}")
    print(f"  Source      : {source}")
    print(f"  Confidence  : {f'{confidence:.2f}' if confidence is not None else '—'}")
    print(f"  Durée       : {elapsed}s")

    if not data:
        print(f"  Résultat    : AUCUN MATCH")
        print(f"{'─'*60}\n")
        return

    if "pappers" in source:
        _print_pappers(data)
    elif "yahoo" in source:
        _print_yahoo(data)

    print(f"{'─'*60}\n")


def _print_pappers(data: dict):
    meta     = data.get("_meta", {})
    identite = data.get("identite", {})
    pairs    = identite.get("main_bloc_pairs", {})
    print(f"  Nom         : {identite.get('company_name_raw') or pairs.get('Raison sociale', '—')}")
    print(f"  SIREN       : {identite.get('siren_raw', '—')}")
    print(f"  Forme jur.  : {identite.get('legal_form_raw', '—')}")
    print(f"  Création    : {identite.get('creation_raw', '—')}")
    print(f"  Effectif    : {identite.get('effectif_raw', '—')}")
    print(f"  Adresse     : {identite.get('adresse_raw', '—')}")
    print(f"  Match       : {meta.get('match_score', '—')}/100 — {meta.get('match_level', '')}")
    fin = data.get("finances_raw", {})
    ca_lines = fin.get("ca_lines", [])
    if ca_lines:
        print(f"  CA (extrait): {ca_lines[0][:80]}")


def _print_yahoo(data: dict):
    print(f"  Ticker      : {data.get('symbol', '—')}")
    print(f"  Nom         : {data.get('longName') or data.get('longname', '—')}")
    print(f"  Exchange    : {data.get('exchange', '—')}")
    print(f"  Secteur     : {data.get('sector', '—')}")
    print(f"  Industrie   : {data.get('industry', '—')}")
    mc = data.get("marketCap")
    if mc:
        print(f"  Mkt Cap     : {mc/1e9:.2f} Md$")
    rev = data.get("totalRevenue")
    if rev:
        print(f"  CA          : {rev/1e6:.1f} M$")
    margin = data.get("profitMargins")
    if margin is not None:
        print(f"  Marge nette : {margin*100:.1f}%")
    growth = data.get("revenueGrowth")
    if growth is not None:
        print(f"  Croissance  : {growth*100:+.1f}%")
    print(f"  Match score : {data.get('_match_score', 0):.2f} ({data.get('_match_method', '—')})")
    summary = data.get("longBusinessSummary") or ""
    if summary:
        print(f"  Description : {summary[:120]}…")


def _save_result(company: dict):
    name = company.get("company_name") or "unknown"
    slug = name.lower().replace(" ", "_")[:40]
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"{slug}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(company, f, indent=2, ensure_ascii=False)
    logger.info(f"Sauvegardé → {path}")
    print(f"  Fichier     : {path.name}")


async def run_batch(batch_path: str):
    path = Path(batch_path)
    if not path.exists():
        print(f"Fichier introuvable : {batch_path}")
        sys.exit(1)
    companies = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(companies, dict):
        companies = [companies]
    print(f"\n Batch : {len(companies)} entreprise(s)\n")
    results = []
    stats   = {"ok": 0, "no_match": 0, "error": 0}
    for i, c in enumerate(companies, 1):
        label = c.get("name") or c.get("company_name", "?")
        print(f"\n[{i}/{len(companies)}] {label}")
        try:
            result = await run_one(c)
            stats["ok" if result.get("finance_data") else "no_match"] += 1
            results.append(result)
        except Exception as e:
            logger.error(f"Erreur sur {c} : {e}")
            stats["error"] += 1
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_out = OUTPUT_DIR / f"batch_{ts}.json"
    with open(batch_out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n{'='*60}")
    print(f"  Matchés    : {stats['ok']}/{len(companies)}")
    print(f"  No match   : {stats['no_match']}/{len(companies)}")
    print(f"  Erreurs    : {stats['error']}/{len(companies)}")
    print(f"  Batch JSON : {batch_out.name}")
    print(f"{'='*60}\n")


async def run_interactive():
    print("\n Finance Runner — Mode interactif")
    print(" (laisser vide = None, Ctrl+C pour quitter)\n")
    while True:
        print("─" * 40)
        name = input("Nom entreprise    : ").strip()
        if not name:
            print("Le nom est obligatoire.")
            continue
        country = input("Pays              : ").strip() or None
        url     = input("URL               : ").strip() or None
        address = input("Adresse           : ").strip() or None
        await run_one({"name": name, "country": country, "url": url, "address": address})
        again = input("Tester une autre ? (o/n) : ").strip().lower()
        if again not in ("o", "oui", "y", "yes"):
            break


async def main():
    parser = argparse.ArgumentParser(description="Finance Runner — outil de test autonome")
    parser.add_argument("--name",    type=str)
    parser.add_argument("--country", type=str)
    parser.add_argument("--url",     type=str)
    parser.add_argument("--address", type=str)
    parser.add_argument("--batch",   type=str)
    args = parser.parse_args()

    if args.batch:
        await run_batch(args.batch)
    elif args.name:
        await run_one({"name": args.name, "country": args.country, "url": args.url, "address": args.address})
    else:
        await run_interactive()


if __name__ == "__main__":
    asyncio.run(main())