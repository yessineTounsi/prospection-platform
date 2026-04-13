"""
Test Phase 7 — NLP Enricher (spaCy)
Charge le v4 et applique l'enrichissement NLP.
"""
import sys
sys.path.insert(0, ".")

import json
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from extraction.nlp_enricher import enrich_with_nlp

# ── Choisir le fichier v4 à enrichir ──────────────────────────────────────────
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--file", default="output/json/www_vermeg_com_v4.json",
                    help="Chemin vers le v4 JSON")
args = parser.parse_args()

with open(args.file, encoding="utf-8") as f:
    data = json.load(f)

# Supporter un fichier contenant une liste ou un seul objet
companies = data if isinstance(data, list) else [data]

for company in companies:
    name = company.get("company_name") or company.get("website_url", "?")
    print(f"\n{'='*60}")
    print(f"Enrichissement NLP : {name}")
    print('='*60)

    # Afficher les champs null avant
    fields = ["team_leaders", "reviews", "founded_year", "employees_count", "revenue"]
    print("\nChamps null avant NLP :")
    for f in fields:
        if company.get(f) is None:
            print(f"  {f}: null")

    company = enrich_with_nlp(company)

    # Afficher les nouveaux champs
    print("\nRésultats après NLP :")

    new_fields = [
        "team_leaders", "reviews", "founded_year", "employees_count", "revenue",
        "key_metrics", "certifications", "technologies", "sectors",
        "locations_geo", "orgs_mentioned",
    ]
    for f in new_fields:
        val = company.get(f)
        if val is None:
            print(f"  {f}: null")
        elif isinstance(val, list):
            print(f"  {f} ({len(val)}) : {val[:3]}{'...' if len(val) > 3 else ''}")
        elif isinstance(val, dict):
            print(f"  {f} : {val}")
        else:
            print(f"  {f} : {val}")

    # Sauvegarder
    out_path = args.file.replace("_v4.json", "_v5.json").replace("_v3.json", "_v5.json")
    with open(out_path, "w", encoding="utf-8") as f_out:
        json.dump(company, f_out, indent=4, ensure_ascii=False)
    print(f"\nSauvegardé : {out_path}")
