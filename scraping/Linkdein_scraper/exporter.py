import csv
import json
import re
from pathlib import Path
from config import OUTPUT_CSV, OUTPUT_JSON
from utils import clean_text, clean_url

FIELDNAMES = ["slug", "nom", "taille", "secteur", "specialites", "services",
              "site_web", "membre_nom", "membre_poste", "membre_url"]


# ─────────────────────────────────────────────
#  JSON
# ─────────────────────────────────────────────
def save_to_json(companies_data: list):
    output = []
    for company in companies_data:
        info, membres = company["info"], company["membres"]
        output.append({
            "slug"        : clean_text(info.get("slug", "")),
            "nom"         : clean_text(info.get("nom", "")),
            "taille"      : clean_text(info.get("taille", "")),
            "secteur"     : clean_text(info.get("secteur", "")),
            "specialites" : clean_text(info.get("specialites", "")),
            "services"    : clean_text(info.get("services", "")),
            "site_web"    : clean_url(info.get("site_web", "")),
            "membres": [
                {
                    "nom"       : clean_text(m.get("nom", "")),
                    "poste"     : clean_text(m.get("poste", "")) if clean_text(m.get("poste", "")) != clean_text(m.get("nom", "")) else "",
                    "profil_url": clean_url(m.get("profil_url", "")),
                }
                for m in membres
            ],
        })

    existing = []
    if OUTPUT_JSON.exists():
        try:
            existing = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    slugs = {e["slug"]: i for i, e in enumerate(existing)}
    for entry in output:
        if entry["slug"] in slugs:
            existing[slugs[entry["slug"]]] = entry
        else:
            existing.append(entry)

    OUTPUT_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📦 JSON → {OUTPUT_JSON} ({len(existing)} entreprises)")


# ─────────────────────────────────────────────
#  CSV
# ─────────────────────────────────────────────
def _build_rows(company: dict) -> list:
    info, members = company["info"], company["membres"]
    base = {k: clean_text(info.get(k, "")) for k in ["slug","nom","taille","secteur","specialites","services"]}
    base["site_web"] = clean_url(info.get("site_web", ""))
    rows = []
    if members:
        for m in members:
            poste = clean_text(m.get("poste", ""))
            nom   = clean_text(m.get("nom", ""))
            rows.append({**base,
                "membre_nom"  : nom,
                "membre_poste": poste if poste != nom else "",
                "membre_url"  : clean_url(m.get("profil_url", "")),
            })
    else:
        rows.append({**base, "membre_nom": "", "membre_poste": "", "membre_url": ""})
    return rows


def save_company_csv(company: dict):
    nom = clean_text(company["info"].get("nom", company["info"].get("slug", "unknown")))
    safe = re.sub(r'[^\w\s-]', '', nom).strip().replace(" ", "_")
    path = Path(f"{safe}.csv")
    rows = _build_rows(company)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerows(rows)
    print(f"   💾 {path.name} ({len(rows)} lignes)")
    return rows


def save_to_csv(companies_data: list):
    all_rows = []
    for company in companies_data:
        all_rows.extend(save_company_csv(company))

    global_exists = OUTPUT_CSV.exists()
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not global_exists:
            w.writeheader()
        w.writerows(all_rows)
    print(f"📄 CSV global → {OUTPUT_CSV} ({len(all_rows)} lignes ajoutées)")