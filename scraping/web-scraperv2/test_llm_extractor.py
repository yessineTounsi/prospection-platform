"""
Test Phase 6 — LLM Extractor
Charge le v3 de confoline et extrait les champs nuls.
"""
import sys
sys.path.insert(0, ".")

import json
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from extraction.llm_extractor import extract_null_fields

# Charger le v3
with open("output/json/www_vermeg_com_v3.json", encoding="utf-8") as f:
    company = json.load(f)

print("Champs nuls avant extraction :")
fields = ["company_name","description","services","clients","team_leaders","founded_year","employees_count","revenue","reviews"]
for f in fields:
    print(f"  {f}: {company.get(f)}")

print("\n--- Phase 6 : Extraction LLM ---\n")
company = extract_null_fields(company)

print("\nChamps après extraction :")
for f in fields:
    val = company.get(f)
    if isinstance(val, list):
        print(f"  {f}: {val[:3]}{'...' if len(val) > 3 else ''}")
    else:
        print(f"  {f}: {val}")

# Sauvegarder
with open("output/json/www_vermeg_com_v4.json", "w", encoding="utf-8") as f:
    json.dump(company, f, indent=4, ensure_ascii=False)

print("\nSauvegardé : output/json/www_vermeg_com_v4.json")
