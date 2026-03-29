"""
pappers_scraper.py — Extraction brute Pappers → raw JSON
Rôle unique : scraper et sauvegarder les données BRUTES sans aucun traitement.
Le processor s'occupe du reste.

Usage : python pappers_scraper.py
Output: raw/capgemini_raw.json
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import re
import json
import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from config import CRAWL4AI_HEADLESS, CRAWL4AI_DELAY, USER_AGENTS

RAW_DIR = Path("raw")
RAW_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# PLAYWRIGHT — fetcher avec scroll + interception XHR
# ══════════════════════════════════════════════════════════════════

async def get_page_data(url: str) -> dict:
    """
    Charge une page Pappers et retourne :
    - html      : contenu HTML complet après rendu JS
    - xhr_data  : dict de toutes les réponses JSON interceptées (clé = url partielle)
    """
    result = {"html": None, "xhr_data": {}}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=CRAWL4AI_HEADLESS)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            locale="fr-FR",
        )
        page = await context.new_page()

        # Bloquer images/fonts pour aller plus vite
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}",
            lambda r: r.abort()
        )

        # ── Intercepter toutes les réponses JSON (XHR/fetch) ──────
        async def handle_response(response):
            try:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type and response.status == 200:
                    resp_url = response.url
                    # Filtrer uniquement les appels API Pappers pertinents
                    if any(k in resp_url for k in [
                        "pappers.fr/api", "/entreprise/", "/finances",
                        "/dirigeants", "/bilans", "/comptes"
                    ]):
                        try:
                            data = await response.json()

                            # ── Exclure les données inutiles ──────────
                            # Supprimer les clés parasites
                            KEYS_TO_EXCLUDE = [
                                "entreprises", "liens_entreprises_personnes",
                                "liens_entreprises_entreprises", "personnes",
                                "beneficiaires_effectifs"
                            ]
                            if isinstance(data, dict):
                                data = {k: v for k, v in data.items()
                                        if k not in KEYS_TO_EXCLUDE}

                            # Garder uniquement si contient des données utiles
                            USEFUL_KEYS = [
                                "chiffre_affaires", "ca", "resultat", "resultat_net",
                                "effectif", "nb_salaries", "finances", "bilans",
                                "dirigeants", "representants"
                            ]
                            if isinstance(data, dict) and not any(
                                k in data for k in USEFUL_KEYS
                            ):
                                pass  # Skip — pas de données utiles
                            else:
                                key = resp_url.split("pappers.fr")[-1][:80]
                                result["xhr_data"][key] = data
                                print(f"    [XHR] {key[:60]}")
                        except Exception:
                            pass
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            await page.wait_for_timeout(CRAWL4AI_DELAY * 1000)

            # Scroll pour déclencher le lazy-loading des sections financières
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            await page.wait_for_timeout(1200)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 2/3)")
            await page.wait_for_timeout(1200)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)  # Attendre les derniers XHR

            result["html"] = await page.content()

        except Exception as e:
            print(f"  ❌ Playwright : {e}")
        finally:
            await browser.close()

    return result


# ══════════════════════════════════════════════════════════════════
# EXTRACTION BRUTE HTML → dict (sans traitement, sans calcul)
# ══════════════════════════════════════════════════════════════════

def extract_raw(html: str, pappers_url: str, xhr_data: dict) -> dict:
    """
    Extrait TOUTES les données disponibles sans nettoyer ni calculer.
    Les valeurs sont stockées telles quelles : chaînes brutes, listes brutes.
    """
    soup      = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(separator="\n", strip=True)

    raw = {
        "_meta": {
            "source":      "pappers.fr",
            "url":         pappers_url,
            "scraped_at":  datetime.now(timezone.utc).isoformat(),
            "has_xhr_data": bool(xhr_data),
            "xhr_keys":    list(xhr_data.keys()),
        },
        "identite":   {},
        "dirigeants": [],
        "finances_raw": {},
        "html_tables": [],
        "xhr_finances": {},
        "texte_brut_sections": {},
    }

    # ── 1. Identité ───────────────────────────────────────────────
    h1 = soup.find("h1")
    if h1:
        raw["identite"]["company_name_raw"] = h1.get_text(strip=True)

    # Bloc principal table-container (tel quel)
    main_bloc = soup.find("div", class_="table-container")
    if main_bloc:
        text  = main_bloc.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        pairs = {}
        for i, line in enumerate(lines):
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            if nxt and line.endswith(":"):
                pairs[line.rstrip(":")] = nxt
        raw["identite"]["main_bloc_pairs"] = pairs

    # Regex identifiants — valeurs brutes sans nettoyage
    patterns_id = {
        "siren_raw":       r'(?:SIREN|Siren)[^\d]*(\d[\d\s]{8,10})',
        "siret_raw":       r'(?:SIRET|Siret)[^\d]*(\d[\d\s]{13,16})',
        "vat_raw":         r'(FR\s?\d{2}\s?\d{9})',
        "naf_raw":         r'(\d{4}[A-Z])',
        "capital_raw":     r'Capital social[^\d]*([\d\s\u202f\xa0,\.]+\s*(?:€|EUR)?)',
        "legal_form_raw":  r'Forme juridique\s*:?\s*([^\n]{3,80})',
        "creation_raw":    r'(?:Cr[eé]ation|Immatriculat[^\n]{0,20})\s*:?\s*([^\n]{4,30})',
        "effectif_raw":    r'(?:Effectif|Salari[eé]s?)[^\n]*\n([^\n]{1,50})',
        "adresse_raw":     r'(?:Adresse|Si[eè]ge)[^\n]*\n([^\n]{5,120})',
        "activite_raw":    r'(?:Activit[eé]|Secteur)[^\n]*\n([^\n]{5,100})',
    }
    for key, pat in patterns_id.items():
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            raw["identite"][key] = m.group(1).strip()

    # ── 2. Dirigeants — liste brute complète ─────────────────────
    for d in soup.find_all(class_="dirigeant"):
        text_parts = [p.strip() for p in d.get_text(separator="|", strip=True).split("|") if p.strip()]
        if text_parts:
            # Stocker tout brut, le processor filtrera
            raw["dirigeants"].append({
                "parts_raw": text_parts,
                "html_raw":  str(d)[:500],
            })

    # ── 3. Tous les tableaux HTML (finances, historique...) ───────
    for i, table in enumerate(soup.find_all("table")):
        rows = []
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if rows:
            raw["html_tables"].append({
                "table_index": i,
                "rows":        rows,
                "row_count":   len(rows),
            })

    # ── 4. Sections financières — texte brut ─────────────────────
    finance_selectors = [
        ("finances_bloc",    "finances-bloc"),
        ("section_finances", "section-finances"),
        ("chiffres_cles",    "chiffres-cles"),
        ("bilans",           "bilans"),
    ]
    for label, cls in finance_selectors:
        blocs = soup.find_all(class_=re.compile(cls, re.IGNORECASE))
        if blocs:
            raw["texte_brut_sections"][label] = [
                b.get_text(separator="\n", strip=True) for b in blocs
            ]

    # Recherche par ID
    for id_sel in ["finances", "financier", "bilans", "chiffres"]:
        el = soup.find(id=re.compile(id_sel, re.IGNORECASE))
        if el:
            raw["texte_brut_sections"][f"id_{id_sel}"] = el.get_text(separator="\n", strip=True)

    # ── 5. Lignes financières clés — regex larges (brut) ─────────
    finance_patterns = {
        "ca_lines":         r"(?:Chiffre d.affaires|CA\b)[^\n]*\n[^\n]+",
        "resultat_lines":   r"(?:R[eé]sultat net|B[eé]n[eé]fice net)[^\n]*\n[^\n]+",
        "ebitda_lines":     r"(?:EBITDA|EBE|Exc[eé]dent brut)[^\n]*\n[^\n]+",
        "bilan_lines":      r"(?:Total.*bilan|Total.*actif)[^\n]*\n[^\n]+",
        "capitaux_lines":   r"(?:Capitaux propres|Fonds propres)[^\n]*\n[^\n]+",
        "dettes_lines":     r"(?:Dettes financ|Endettement)[^\n]*\n[^\n]+",
        "effectif_hist":    r"(?:Effectif|Salari[eé]s?).*?(\d{4}).*?\n[^\n]+",
    }
    for key, pat in finance_patterns.items():
        matches = re.findall(pat, full_text, re.IGNORECASE)
        if matches:
            raw["finances_raw"][key] = matches[:10]  # max 10 occurrences

    # Toutes les années détectées + contexte
    year_contexts = re.findall(r'(20\d{2})[^\n]*\n([^\n]{0,100})', full_text)
    if year_contexts:
        raw["finances_raw"]["year_contexts_raw"] = [
            {"year": y, "context": c} for y, c in year_contexts[:30]
        ]

    # ── 6. Données XHR interceptées ──────────────────────────────
    raw["xhr_finances"] = xhr_data  # Stocké tel quel

    # ── 7. Texte brut global (pour fallback processor) ────────────
    raw["full_text_length"] = len(full_text)
    # Stocker un extrait des 3000 premiers caractères pour debug
    raw["full_text_preview"] = full_text[:3000]

    return raw


# ══════════════════════════════════════════════════════════════════
# MATCHING (inchangé — logique métier uniquement)
# ══════════════════════════════════════════════════════════════════

def compute_match_score(raw_data: dict, company_name: str, address: str = None) -> dict:
    identite = raw_data.get("identite", {})
    pairs    = identite.get("main_bloc_pairs", {})

    candidate_name = (
        identite.get("company_name_raw") or
        pairs.get("Raison sociale") or ""
    ).lower().strip()
    query_name = company_name.lower().strip()

    score, detail = 0, []

    if candidate_name == query_name:
        score = max(score + 40, 60)
        detail.append("nom exact +40")
    elif query_name in candidate_name or candidate_name in query_name:
        score += 25
        detail.append("nom partiel +25")
    else:
        qw = set(query_name.split())
        cw = set(candidate_name.split())
        common = qw & cw
        if common:
            pts = int(15 * len(common) / max(len(qw), len(cw)))
            score += pts
            detail.append(f"mots communs +{pts}")

    if address:
        addr_raw = identite.get("adresse_raw", "")
        cp_q = re.findall(r'\b\d{5}\b', address)
        cp_c = re.findall(r'\b\d{5}\b', addr_raw)
        if cp_q and cp_c and cp_q[0] == cp_c[0]:
            score += 40
            detail.append(f"code postal exact ({cp_q[0]}) +40")
        else:
            vq = set(re.sub(r'\d', '', address).lower().split()) - {"rue","avenue","boulevard","place","chemin",""}
            vc = set(re.sub(r'\d', '', addr_raw).lower().split()) - {"rue","avenue","boulevard","place","chemin",""}
            if vq & vc:
                score += 20
                detail.append("ville commune +20")

    return {
        "score":  min(score, 100),
        "detail": " | ".join(detail),
        "level":  "✅ Excellent" if score >= 80 else "⚠️ Moyen" if score >= 50 else "❌ Faible",
    }


# ══════════════════════════════════════════════════════════════════
# RECHERCHE + SCRAPE
# ══════════════════════════════════════════════════════════════════

async def scrape_company(company_name: str, address: str = None, max_results: int = 3) -> Path | None:
    """
    Cherche sur Pappers, sélectionne le meilleur match, scrape et sauvegarde raw JSON.
    Retourne le chemin du fichier sauvegardé.
    """
    search_url = f"https://www.pappers.fr/recherche?q={company_name.replace(' ', '+')}"
    print(f"\n  Recherche : {search_url}")

    page_data = await get_page_data(search_url)
    if not page_data["html"]:
        print("  ❌ Impossible de charger la page de recherche")
        return None

    soup  = BeautifulSoup(page_data["html"], "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/entreprise/" in href:
            full = f"https://www.pappers.fr{href}" if href.startswith("/") else href
            full = full.split("?")[0]
            if full not in links:
                links.append(full)

    if not links:
        print("  ❌ Aucun résultat")
        return None

    print(f"  {len(links)} résultats — scrape des {min(max_results, len(links))} premiers...")

    best_path  = None
    best_score = -1

    for i, url in enumerate(links[:max_results]):
        print(f"\n  [{i+1}] {url}")
        page_data = await get_page_data(url)
        if not page_data["html"]:
            continue

        raw_data = extract_raw(page_data["html"], url, page_data["xhr_data"])
        match    = compute_match_score(raw_data, company_name, address)

        raw_data["_meta"]["match_score"]  = match["score"]
        raw_data["_meta"]["match_detail"] = match["detail"]
        raw_data["_meta"]["match_level"]  = match["level"]

        # Nom de fichier safe
        slug = re.sub(r'[^\w]', '_', url.split("/entreprise/")[-1])[:50]
        path = RAW_DIR / f"{slug}_raw.json"
        path.write_text(json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8")

        xhr_count = len(page_data["xhr_data"])
        tbl_count = len(raw_data["html_tables"])
        print(f"      {match['level']} (score: {match['score']}/100) | {match['detail']}")
        print(f"      XHR interceptés: {xhr_count} | Tableaux HTML: {tbl_count}")
        print(f"      Sauvegardé → {path}")

        if match["score"] > best_score:
            best_score = match["score"]
            best_path  = path

        if best_score >= 80:
            break

        await asyncio.sleep(random.uniform(2, 3))

    return best_path


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

async def main():
    print("=== Pappers Scraper — Extraction brute ===\n")
    company_name = input("Nom de l'entreprise : ").strip()
    address      = input("Adresse (optionnel) : ").strip() or None

    path = await scrape_company(company_name, address)

    if path:
        print(f"\nFichier raw prêt : {path}")
        print("Lancez ensuite : python pappers_processor.py")
    else:
        print("\n❌ Aucun résultat sauvegardé")


if __name__ == "__main__":
    asyncio.run(main())