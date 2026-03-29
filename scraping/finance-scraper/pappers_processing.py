"""
pappers_processor.py — Data processing du raw JSON Pappers
Rôle unique : lire un raw JSON et produire un JSON propre, enrichi, prêt pour la sales intelligence.

Usage : python pappers_processor.py
Input : raw/xxx_raw.json   (ou le dernier fichier raw disponible)
Output: processed/xxx_processed.json
"""
import re
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAW_DIR       = Path("raw")
PROCESSED_DIR = Path("processed")
PROCESSED_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════
# HELPERS — nettoyage de valeurs brutes
# ══════════════════════════════════════════════════════════════════

def clean_text(val: str) -> str | None:
    """Supprime espaces, caractères spéciaux inutiles."""
    if not val:
        return None
    val = val.strip().replace('\u202f', ' ').replace('\xa0', ' ')
    val = re.sub(r'\s+', ' ', val)
    return val if val else None


def clean_amount(raw: str) -> dict | None:
    """
    Convertit une chaîne financière brute en dict normalisé.
    Exemples :
      "1 234 567 €"  → {"value": 1234567, "unit": "EUR", "raw": "1 234 567 €"}
      "22,5 M€"      → {"value": 22500000, "unit": "EUR", "raw": "22,5 M€"}
      "430M"         → {"value": 430000000, "unit": "EUR", "raw": "430M"}
    """
    if not raw:
        return None
    raw = str(raw).strip().replace('\u202f', '').replace('\xa0', '').replace(' ', '')

    if any(x in raw.lower() for x in ['indisponible', 'confidentiel', 'n/a', 'nc']):
        return None

    # Détecter unité
    multiplier = 1
    if re.search(r'[Gg]€|[Gg]B|milliard', raw, re.IGNORECASE):
        multiplier = 1_000_000_000
    elif re.search(r'[Mm]€|[Mm]$|million', raw, re.IGNORECASE):
        multiplier = 1_000_000
    elif re.search(r'[Kk]€|[Kk]$|millier', raw, re.IGNORECASE):
        multiplier = 1_000

    # Extraire le nombre (gère virgule décimale française)
    num_str = re.sub(r'[^\d,.\-]', '', raw)
    num_str = num_str.replace(',', '.')
    # Supprimer points de milliers si plusieurs points
    if num_str.count('.') > 1:
        num_str = num_str.replace('.', '', num_str.count('.') - 1)

    try:
        value = float(num_str) * multiplier
        return {
            "value": int(value) if value == int(value) else round(value, 2),
            "unit":  "EUR",
            "raw":   raw,
        }
    except (ValueError, OverflowError):
        return None


def clean_siren(raw: str) -> str | None:
    """Normalise SIREN : supprime espaces, garde 9 chiffres."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    return digits if len(digits) == 9 else None


def clean_siret(raw: str) -> str | None:
    """Normalise SIRET : supprime espaces, garde 14 chiffres."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    return digits if len(digits) == 14 else None


def clean_year(raw: str) -> int | None:
    """Extrait une année valide (1900–2100)."""
    if not raw:
        return None
    m = re.search(r'((?:19|20)\d{2})', str(raw))
    if m:
        y = int(m.group(1))
        return y if 1900 <= y <= 2100 else None
    return None


def clean_naf(raw: str) -> str | None:
    """Normalise code NAF/APE : 4 chiffres + lettre."""
    if not raw:
        return None
    m = re.search(r'(\d{4}[A-Z])', str(raw).upper())
    return m.group(1) if m else None


def clean_legal_form(raw: str) -> str | None:
    """Nettoie la forme juridique, enlève le bruit après le nom."""
    if not raw:
        return None
    # Couper au premier chiffre ou keyword parasite
    clean = re.split(r'(?:Num[eé]ro|Capital|Inscr|TVA|\d{5})', raw)[0]
    return clean_text(clean)


def company_age(founded_year: int | None) -> int | None:
    """Calcule l'ancienneté en années."""
    if not founded_year:
        return None
    return datetime.now().year - founded_year


# ══════════════════════════════════════════════════════════════════
# PROCESSING DIRIGEANTS
# ══════════════════════════════════════════════════════════════════

TITRES_VALIDES = {
    "président", "directeur général", "directrice générale",
    "gérant", "co-gérant", "pdg", "dg", "ceo", "cto", "cfo", "coo",
    "associé gérant", "administrateur délégué", "vice-président",
    "directeur", "directrice", "président du conseil"
}
TITRES_EXCLUS = {
    "ancien", "commissaire", "auditeur", "liquidateur",
    "représentant permanent", "censeur"
}
ENTITES_EXCLUES = {
    "SA", "SCI", "SARL", "SAS", "SASU", "EURL", "SNC",
    "PRICEWATERHOUSE", "MAZARS", "FORVIS", "BDO", "KPMG", "DELOITTE", "EY"
}


def process_dirigeants(raw_list: list) -> list:
    """
    Transforme les dirigeants bruts en liste propre de décideurs actifs.
    Retourne uniquement les vrais dirigeants avec titre valide.
    """
    result = []
    seen   = set()

    for item in raw_list:
        parts = item.get("parts_raw", [])
        if len(parts) < 2:
            continue

        nom   = clean_text(parts[0]) or ""
        titre = clean_text(parts[1]) or ""

        # Dédoublonner
        key = (nom.lower(), titre.lower())
        if key in seen:
            continue

        # Exclure entités non-personnes
        if any(e in nom.upper() for e in ENTITES_EXCLUES):
            continue

        # Exclure titres entre parenthèses (noms de jeune fille)
        if titre.startswith("(") and titre.endswith(")"):
            continue

        # Exclure anciens dirigeants et non-décideurs
        titre_lower = titre.lower()
        if any(e in titre_lower for e in TITRES_EXCLUS):
            continue

        # Garder uniquement les vrais décideurs
        if not any(t in titre_lower for t in TITRES_VALIDES):
            continue

        # Extraire âge si présent
        age_raw = next((p for p in parts if "ans" in p.lower()), None)
        age_val = None
        if age_raw:
            m = re.search(r'(\d{2})\s*ans', age_raw, re.IGNORECASE)
            if m:
                age_val = int(m.group(1))

        # Extraire date de naissance
        dob = None
        for p in parts:
            m = re.search(r'(\d{2}/\d{4}|\d{4})', p)
            if m and "ans" not in p.lower():
                dob = m.group(1)
                break

        seen.add(key)
        result.append({
            "nom":        nom,
            "titre":      titre,
            "age":        age_val,
            "naissance":  dob,
            "is_pdg":     any(t in titre_lower for t in ["pdg", "président du conseil", "président-directeur"]),
            "is_dg":      any(t in titre_lower for t in ["directeur général", "directrice générale", "dg", "ceo"]),
        })

    return result


# ══════════════════════════════════════════════════════════════════
# PROCESSING FINANCES — tableaux HTML + XHR + regex
# ══════════════════════════════════════════════════════════════════

def extract_year_from_header(cells: list) -> list:
    """Retourne les indices des colonnes qui sont des années (20xx)."""
    return [i for i, c in enumerate(cells) if re.match(r'^20\d{2}$', str(c).strip())]


def process_finances(raw: dict) -> dict:
    """
    Tente d'extraire des données financières propres depuis :
    1. Les données XHR (priorité maximale — JSON structuré)
    2. Les tableaux HTML
    3. Les extraits texte brut (fallback regex)
    """
    finances = {
        "source":           None,
        "annees_disponibles": [],
        "historique":       {},   # {"2023": {"ca": ..., "resultat_net": ..., ...}}
        "derniere_annee":   None,
        "indicateurs_cles": {},
    }

    # ── Priorité 1 : données XHR (JSON propre intercepté) ────────
    xhr = raw.get("xhr_finances", {})
    if xhr:
        finances["source"] = "xhr"
        for key, data in xhr.items():
            _parse_xhr_finances(data, finances)

    # ── Priorité 2 : tableaux HTML ────────────────────────────────
    if not finances["historique"]:
        tables = raw.get("html_tables", [])
        for table in tables:
            rows = table.get("rows", [])
            if not rows:
                continue
            _parse_table_finances(rows, finances)

    # ── Priorité 3 : fallback regex sur texte brut ────────────────
    if not finances["historique"]:
        finances["source"] = "regex_fallback"
        fin_raw = raw.get("finances_raw", {})
        _parse_regex_finances(fin_raw, finances)

    # ── Calculer les indicateurs si données disponibles ──────────
    if finances["historique"]:
        _compute_indicators(finances)
        finances["annees_disponibles"] = sorted(finances["historique"].keys(), reverse=True)
        finances["derniere_annee"]     = finances["annees_disponibles"][0] if finances["annees_disponibles"] else None

    return finances


def _parse_xhr_finances(data: dict | list, finances: dict):
    """Parse une réponse XHR Pappers — s'adapte selon la structure."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _parse_xhr_finances(item, finances)
        return

    if not isinstance(data, dict):
        return

    # Chercher des années dans les clés
    for key, val in data.items():
        year_m = re.search(r'20\d{2}', str(key))
        if year_m:
            year = year_m.group(0)
            if year not in finances["historique"]:
                finances["historique"][year] = {}
            if isinstance(val, (int, float)):
                # Deviner le type par le nom de la clé
                kl = key.lower()
                if any(k in kl for k in ["ca", "chiffre", "turnover", "revenue"]):
                    finances["historique"][year]["ca"] = {"value": val, "unit": "EUR", "raw": str(val)}
                elif any(k in kl for k in ["resultat", "net", "profit", "benefice"]):
                    finances["historique"][year]["resultat_net"] = {"value": val, "unit": "EUR", "raw": str(val)}

        # Récursion sur les valeurs dict
        if isinstance(val, dict):
            _parse_xhr_finances(val, finances)


def _parse_table_finances(rows: list, finances: dict):
    """
    Analyse un tableau HTML pour en extraire l'historique financier.
    Stratégie : détecter la ligne d'en-tête avec les années, puis mapper les lignes de données.
    """
    LABEL_MAP = {
        # CA
        ("chiffre", "affaires"): "ca",
        ("ca",):                 "ca",
        ("revenus",):            "ca",
        ("turnover",):           "ca",
        # Résultat net
        ("resultat", "net"):     "resultat_net",
        ("benefice", "net"):     "resultat_net",
        ("profit", "net"):       "resultat_net",
        # EBITDA
        ("ebitda",):             "ebitda",
        ("ebe",):                "ebitda",
        ("excedent", "brut"):    "ebitda",
        # Résultat exploitation
        ("resultat", "exploit"): "resultat_exploitation",
        ("ebit",):               "resultat_exploitation",
        # Capitaux propres
        ("capitaux", "propres"): "capitaux_propres",
        ("fonds", "propres"):    "capitaux_propres",
        # Total bilan
        ("total", "bilan"):      "total_bilan",
        ("total", "actif"):      "total_bilan",
        # Dettes
        ("dettes", "financ"):    "dettes_financieres",
        ("endettement",):        "dettes_financieres",
        # Effectif
        ("effectif",):           "effectif",
        ("salaries",):           "effectif",
        ("employes",):           "effectif",
    }

    header_row  = None
    year_cols   = {}  # {col_index: "2023"}

    for row in rows:
        # Chercher la ligne d'en-tête avec années
        years_in_row = [(i, c) for i, c in enumerate(row) if re.match(r'^20\d{2}$', str(c).strip())]
        if len(years_in_row) >= 2:
            header_row = row
            year_cols  = {i: c.strip() for i, c in years_in_row}
            continue

        if not year_cols or not row:
            continue

        # Ligne de données
        label_raw = str(row[0]).lower()
        label_raw = re.sub(r'[^\w\s]', ' ', label_raw)
        label_words = set(label_raw.split())

        matched_field = None
        for key_words, field in LABEL_MAP.items():
            if all(kw in label_raw for kw in key_words):
                matched_field = field
                break

        if not matched_field:
            continue

        for col_idx, year in year_cols.items():
            if col_idx < len(row):
                amount = clean_amount(str(row[col_idx]))
                if amount:
                    if year not in finances["historique"]:
                        finances["historique"][year] = {}
                    # Ne pas écraser une valeur existante (XHR prioritaire)
                    if matched_field not in finances["historique"][year]:
                        finances["historique"][year][matched_field] = amount
                        if finances["source"] is None:
                            finances["source"] = "html_table"


def _parse_regex_finances(fin_raw: dict, finances: dict):
    """Fallback : extraire depuis les lignes regex brutes."""
    # Associer les year_contexts à des montants
    year_contexts = fin_raw.get("year_contexts_raw", [])
    for item in year_contexts:
        year    = item.get("year")
        context = item.get("context", "")
        if not year or not context:
            continue

        amounts = re.findall(r'([\d\s]{3,}(?:,\d+)?\s*(?:€|k€|M€|G€)?)', context)
        if amounts and year not in finances["historique"]:
            first_amount = clean_amount(amounts[0])
            if first_amount:
                finances["historique"][year] = {"ca_estimate": first_amount}


def _compute_indicators(finances: dict):
    """Calcule les ratios et taux de croissance à partir de l'historique."""
    hist   = finances["historique"]
    years  = sorted(hist.keys(), reverse=True)
    indic  = finances["indicateurs_cles"]

    if not years:
        return

    latest_year = years[0]
    latest      = hist[latest_year]

    # ── Métriques de la dernière année ───────────────────────────
    if "ca" in latest:
        indic["ca_dernier"] = latest["ca"]

    if "resultat_net" in latest:
        indic["resultat_net_dernier"] = latest["resultat_net"]

    if "ebitda" in latest:
        indic["ebitda_dernier"] = latest["ebitda"]

    # ── Marge nette ───────────────────────────────────────────────
    ca_val  = (latest.get("ca") or {}).get("value")
    res_val = (latest.get("resultat_net") or {}).get("value")
    if ca_val and res_val and ca_val > 0:
        marge = round((res_val / ca_val) * 100, 1)
        indic["marge_nette_pct"] = {"value": marge, "label": f"{marge:+.1f}%"}

    # ── Taux de croissance CA YoY (N vs N-1) ─────────────────────
    if len(years) >= 2:
        prev_year = years[1]
        ca_new = (hist[latest_year].get("ca") or {}).get("value")
        ca_old = (hist[prev_year].get("ca") or {}).get("value")
        if ca_new and ca_old and ca_old != 0:
            growth = round(((ca_new - ca_old) / abs(ca_old)) * 100, 1)
            indic["croissance_ca_yoy"] = {
                "value":    growth,
                "label":    f"{growth:+.1f}%",
                "periode":  f"{prev_year}→{latest_year}",
                "signal":   "forte_croissance" if growth > 15 else
                            "croissance" if growth > 5 else
                            "stable" if growth > -5 else
                            "declin",
            }

    # ── CAGR sur N années ─────────────────────────────────────────
    if len(years) >= 3:
        oldest_year = years[-1]
        ca_latest = (hist[latest_year].get("ca") or {}).get("value")
        ca_oldest = (hist[oldest_year].get("ca") or {}).get("value")
        n_years   = int(latest_year) - int(oldest_year)
        if ca_latest and ca_oldest and ca_oldest > 0 and n_years > 0:
            cagr = round(((ca_latest / ca_oldest) ** (1 / n_years) - 1) * 100, 1)
            indic["cagr_ca"] = {
                "value":   cagr,
                "label":   f"{cagr:+.1f}%/an",
                "periode": f"{oldest_year}–{latest_year}",
                "n_years": n_years,
            }

    # ── Ratio dettes / capitaux propres ───────────────────────────
    dettes_val  = (latest.get("dettes_financieres") or {}).get("value")
    capitaux_val= (latest.get("capitaux_propres") or {}).get("value")
    if dettes_val and capitaux_val and capitaux_val != 0:
        ratio = round(dettes_val / capitaux_val, 2)
        indic["ratio_dettes_capitaux"] = {
            "value": ratio,
            "label": f"{ratio:.2f}x",
            "signal": "sain" if ratio < 1 else "surveiller" if ratio < 2 else "risque",
        }

    # ── Signal global pour sales intelligence ─────────────────────
    signals = []
    growth_signal = (indic.get("croissance_ca_yoy") or {}).get("signal")
    if growth_signal in ("forte_croissance", "croissance"):
        signals.append("CA en hausse → budget probablement disponible")
    elif growth_signal == "declin":
        signals.append("CA en baisse → cycle d'achat prudent")

    marge = (indic.get("marge_nette_pct") or {}).get("value")
    if marge is not None:
        if marge > 10:
            signals.append("Bonne rentabilité → capacité d'investissement")
        elif marge < 0:
            signals.append("Pertes nettes → risque de credit")

    ratio_signal = (indic.get("ratio_dettes_capitaux") or {}).get("signal")
    if ratio_signal == "risque":
        signals.append("Endettement élevé → prudence")

    indic["sales_signals"] = signals


# ══════════════════════════════════════════════════════════════════
# PROCESSOR PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def process(raw: dict) -> dict:
    """
    Transforme un raw dict en dict processé, propre et enrichi.
    Structure de sortie stable et documentée.
    """
    identite = raw.get("identite", {})
    pairs    = identite.get("main_bloc_pairs", {})

    # ── Identité ──────────────────────────────────────────────────
    company_name_raw = identite.get("company_name_raw") or pairs.get("Raison sociale", "")
    founded_raw      = identite.get("creation_raw") or pairs.get("Création")
    founded_year     = clean_year(founded_raw)

    processed = {
        "_meta": {
            "processed_at":  datetime.now(timezone.utc).isoformat(),
            "source_url":    raw.get("_meta", {}).get("url"),
            "scraped_at":    raw.get("_meta", {}).get("scraped_at"),
            "match_score":   raw.get("_meta", {}).get("match_score"),
            "match_level":   raw.get("_meta", {}).get("match_level"),
        },

        # ── Identification légale ─────────────────────────────────
        "identite": {
            "company_name": clean_text(company_name_raw),
            "siren":        clean_siren(identite.get("siren_raw", "")),
            "siret":        clean_siret(identite.get("siret_raw", "")),
            "vat_number":   clean_text(re.sub(r'\s', '', identite.get("vat_raw", ""))),
            "naf_code":     clean_naf(identite.get("naf_raw", "")),
            "legal_form":   clean_legal_form(identite.get("legal_form_raw", "")),
            "capital_raw":  clean_text(identite.get("capital_raw")),
        },

        # ── Localisation ──────────────────────────────────────────
        "localisation": {
            "adresse_raw": clean_text(identite.get("adresse_raw") or pairs.get("Adresse")),
            "code_postal": _extract_cp(identite.get("adresse_raw", "")),
            "ville":       _extract_ville(identite.get("adresse_raw", "")),
            "pays":        "France",
        },

        # ── Activité ──────────────────────────────────────────────
        "activite": {
            "secteur":       clean_text(identite.get("activite_raw") or pairs.get("Activité")),
            "naf_code":      clean_naf(identite.get("naf_raw", "")),
            "creation_year": founded_year,
            "anciennete_ans": company_age(founded_year),
        },

        # ── Effectif ──────────────────────────────────────────────
        "effectif": _process_effectif(identite.get("effectif_raw") or pairs.get("Effectif", "")),

        # ── Dirigeants ────────────────────────────────────────────
        "dirigeants": process_dirigeants(raw.get("dirigeants", [])),

        # ── Finances (processing complet) ─────────────────────────
        "finances": process_finances(raw),

        # ── Scoring sales intelligence ────────────────────────────
        "sales_score": {},
    }

    # ── Scoring final ─────────────────────────────────────────────
    processed["sales_score"] = compute_sales_score(processed)

    return processed


def _extract_cp(adresse: str) -> str | None:
    """Extrait le code postal d'une adresse."""
    m = re.search(r'\b(\d{5})\b', adresse or "")
    return m.group(1) if m else None


def _extract_ville(adresse: str) -> str | None:
    """Extrait le nom de ville d'une adresse française."""
    m = re.search(r'\d{5}\s+([A-ZÀÂÄÉÈÊËÏÎÔÙÛÜ][A-Za-zÀ-ÿ\s\-]+)', adresse or "")
    return clean_text(m.group(1)) if m else None


def _process_effectif(raw_str: str) -> dict:
    """Extrait et normalise l'effectif."""
    if not raw_str:
        return {"raw": None, "min": None, "max": None, "label": None}

    raw_str = clean_text(raw_str) or ""

    # Format "50 à 99 salariés"
    m = re.search(r'(\d+)\s*à\s*(\d+)', raw_str)
    if m:
        return {"raw": raw_str, "min": int(m.group(1)), "max": int(m.group(2)),
                "label": _effectif_label(int(m.group(2)))}

    # Format "123 salariés"
    m = re.search(r'(\d+)\s*salari', raw_str, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        return {"raw": raw_str, "min": val, "max": val, "label": _effectif_label(val)}

    return {"raw": raw_str, "min": None, "max": None, "label": None}


def _effectif_label(n: int) -> str:
    """Segmentation taille d'entreprise."""
    if n == 0:         return "holding_ou_vide"
    if n < 10:         return "TPE"
    if n < 50:         return "PE"
    if n < 250:        return "ME"
    if n < 5000:       return "ETI"
    return "GE"


# ══════════════════════════════════════════════════════════════════
# SALES INTELLIGENCE SCORE
# ══════════════════════════════════════════════════════════════════

def compute_sales_score(processed: dict) -> dict:
    """
    Calcule un score de priorité prospect (0–100) basé sur les données disponibles.
    Plus le score est élevé, plus le prospect est qualifié / opportun.
    """
    score   = 0
    details = []

    identite  = processed.get("identite", {})
    activite  = processed.get("activite", {})
    effectif  = processed.get("effectif", {})
    finances  = processed.get("finances", {})
    indic     = finances.get("indicateurs_cles", {})
    dirigeants= processed.get("dirigeants", [])

    # ── Complétude des données (20 pts) ──────────────────────────
    completude = sum([
        bool(identite.get("siren")),          # 4
        bool(identite.get("vat_number")),      # 4
        bool(activite.get("secteur")),         # 4
        bool(effectif.get("min") is not None), # 4
        bool(dirigeants),                      # 4
    ]) * 4
    score += completude
    details.append(f"complétude: +{completude}/20")

    # ── Taille entreprise (20 pts) ────────────────────────────────
    taille_label = effectif.get("label")
    taille_pts   = {"TPE": 5, "PE": 10, "ME": 15, "ETI": 20, "GE": 20}.get(taille_label, 0)
    score += taille_pts
    if taille_pts:
        details.append(f"taille {taille_label}: +{taille_pts}/20")

    # ── Croissance CA (30 pts) ────────────────────────────────────
    growth = indic.get("croissance_ca_yoy", {})
    if growth:
        g_val   = growth.get("value", 0)
        g_pts   = 30 if g_val > 20 else 25 if g_val > 10 else 20 if g_val > 5 else 10 if g_val > 0 else 0
        score  += g_pts
        details.append(f"croissance CA {growth.get('label', '')}: +{g_pts}/30")

    # ── Rentabilité (15 pts) ──────────────────────────────────────
    marge = indic.get("marge_nette_pct", {})
    if marge:
        m_val = marge.get("value", 0)
        m_pts = 15 if m_val > 10 else 10 if m_val > 5 else 5 if m_val > 0 else 0
        score += m_pts
        details.append(f"marge nette {marge.get('label', '')}: +{m_pts}/15")

    # ── Ancienneté (10 pts) ───────────────────────────────────────
    age = activite.get("anciennete_ans")
    if age:
        a_pts  = 10 if age > 10 else 7 if age > 5 else 4
        score += a_pts
        details.append(f"ancienneté {age} ans: +{a_pts}/10")

    # ── Décideurs identifiés (5 pts) ─────────────────────────────
    if dirigeants:
        score += 5
        details.append(f"{len(dirigeants)} dirigeants identifiés: +5/5")

    # ── Signaux additionnels ──────────────────────────────────────
    sales_signals = indic.get("sales_signals", [])

    final_score = min(score, 100)
    return {
        "score":        final_score,
        "label":        "A" if final_score >= 75 else "B" if final_score >= 50 else "C" if final_score >= 25 else "D",
        "details":      details,
        "signals":      sales_signals,
        "priorite":     "haute" if final_score >= 75 else "moyenne" if final_score >= 50 else "basse",
    }


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    print("=== Pappers Processor — Data processing ===\n")

    # Trouver le(s) fichier(s) raw
    raw_files = sorted(RAW_DIR.glob("*_raw.json"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not raw_files:
        print(f"❌ Aucun fichier raw trouvé dans {RAW_DIR}/")
        print("   Lancez d'abord : python pappers_scraper.py")
        sys.exit(1)

    # Lister les fichiers disponibles
    print(f"Fichiers raw disponibles ({len(raw_files)}) :")
    for i, f in enumerate(raw_files[:10]):
        print(f"  [{i}] {f.name}")

    if len(raw_files) == 1:
        chosen = raw_files[0]
    else:
        idx = input("\nChoisir un fichier [0] : ").strip()
        try:
            chosen = raw_files[int(idx) if idx else 0]
        except (ValueError, IndexError):
            chosen = raw_files[0]

    print(f"\nTraitement : {chosen.name}")
    raw = json.loads(chosen.read_text(encoding="utf-8"))

    # Processing
    processed = process(raw)

    # Sauvegarde
    out_name = chosen.name.replace("_raw.json", "_processed.json")
    out_path = PROCESSED_DIR / out_name
    out_path.write_text(json.dumps(processed, indent=2, ensure_ascii=False), encoding="utf-8")

    # Affichage résumé
    print("\n" + "=" * 60)
    print(json.dumps(processed, indent=2, ensure_ascii=False))
    print("=" * 60)

    # Résumé rapide sales intelligence
    score = processed.get("sales_score", {})
    print(f"\n SALES SCORE : {score.get('score')}/100 — Priorité {score.get('label')} ({score.get('priorite')})")
    for detail in score.get("details", []):
        print(f"   · {detail}")
    for signal in score.get("signals", []):
        print(f"   → {signal}")

    print(f"\nFichier processé : {out_path}")


if __name__ == "__main__":
    main()