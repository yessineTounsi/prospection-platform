"""
yahoo_finance_matcher.py — Matching par website_url (clé universelle)
======================================================================
Stratégie principale  : website_url → domaine → query Yahoo → cross-validation
Fallback automatique  : nom + pays si pas de match par domaine
Clé de jointure       : domaine utilisé pour lier toutes les sources
"""

import json, re, time, random, difflib, hashlib
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse

import requests
import yfinance as yf

YH_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
CACHE_FILE    = Path("cache/yahoo_cache.json")
CACHE_TTL_S   = 86_400
MIN_SCORE     = 0.35
MAX_RETRIES   = 3
DEBUG         = True

LEGAL_SUFFIXES = re.compile(
    r"\b(inc|incorporated|ltd|limited|llc|llp|lp|plc|corp|corporation"
    r"|sa|sas|sarl|sasu|eurl|snc|sca|se|nv|bv|ag|gmbh|kg"
    r"|group|grp|holding|holdings|international|intl|global"
    r"|tech|technology|solutions|services|systems)\b\.?",
    re.IGNORECASE,
)

COUNTRY_EXCHANGES: Dict[str, List[str]] = {
    "US": ["NMS", "NYQ", "NGM", "ASE", "PCX"],
    "FR": ["EPA", "FRA", "PAR"],
    "DE": ["ETR", "FRA", "STU", "MUN"],
    "GB": ["LSE", "IOB"],
    "TN": ["TUN"], "MA": ["CAS"], "AE": ["DFM", "ADS"],
    "SA": ["SAU"], "EG": ["CAI"], "CH": ["SWX", "VTX", "EBS"],
    "NL": ["AMS"], "ES": ["MCE", "MAD"], "IT": ["MIL", "BIT"],
    "JP": ["TYO", "OSA"], "CN": ["SHA", "SHE"], "HK": ["HKG"],
    "IN": ["BSE", "NSI"], "BR": ["SAO"], "AU": ["ASX"],
    "CA": ["TSX", "TOR"], "SG": ["SGX"],
}

NAME_TO_ISO2 = {
    "france": "FR", "french": "FR", "germany": "DE", "allemagne": "DE",
    "uk": "GB", "united kingdom": "GB", "usa": "US", "united states": "US",
    "etats-unis": "US", "us": "US", "spain": "ES", "espagne": "ES",
    "italy": "IT", "italie": "IT", "switzerland": "CH", "suisse": "CH",
    "netherlands": "NL", "pays-bas": "NL", "belgium": "BE", "belgique": "BE",
    "sweden": "SE", "suede": "SE", "tunisia": "TN", "tunisie": "TN",
    "morocco": "MA", "maroc": "MA", "egypt": "EG", "egypte": "EG",
    "saudi arabia": "SA", "arabie saoudite": "SA",
    "uae": "AE", "united arab emirates": "AE",
    "japan": "JP", "japon": "JP", "china": "CN", "chine": "CN",
    "india": "IN", "inde": "IN", "australia": "AU", "australie": "AU",
    "canada": "CA", "brazil": "BR", "bresil": "BR",
    "singapore": "SG", "singapour": "SG", "hong kong": "HK",
}

GENERIC_DOMAINS = {
    "google.com", "linkedin.com", "facebook.com", "twitter.com",
    "instagram.com", "youtube.com", "wikipedia.org",
}


# ══ HELPERS ═══════════════════════════════════════════════════

def _log(msg):
    if DEBUG: print(f"  {msg}")

def _norm(s):
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _strip_legal(name):
    return re.sub(r"\s+", " ", LEGAL_SUFFIXES.sub(" ", name)).strip()

def _iso2(country):
    return NAME_TO_ISO2.get(_norm(country), "")


# ══ EXTRACTION DOMAINE ════════════════════════════════════════

def extract_domain(url: str) -> str:
    """
    Extrait le domaine racine depuis n'importe quelle URL.
    "https://www.capgemini.com/fr/" → "capgemini.com"
    "https://careers.siemens.de"   → "siemens.de"
    """
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        if "." not in host or len(host) < 4:
            return ""
        return host
    except Exception:
        return ""


def extract_root_domain(domain: str) -> str:
    """
    Supprime les sous-domaines.
    "careers.siemens.de" → "siemens.de"
    "blog.capgemini.com" → "capgemini.com"
    """
    if not domain:
        return ""
    parts = domain.split(".")
    compound = {"co.uk","co.jp","co.kr","com.br","com.au","com.ar","com.mx"}
    if len(parts) >= 3 and ".".join(parts[-2:]) in compound:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def domain_score(query_domain: str, candidate_website: str) -> float:
    """
    Score de correspondance domaine ↔ website yfinance.
    1.0  = domaines racines identiques
    0.85 = même racine, sous-domaine différent
    0.60 = même marque, TLD différent (siemens.com vs siemens.de)
    0.0  = aucun rapport
    """
    if not query_domain or not candidate_website:
        return 0.0
    cand = extract_domain(candidate_website)
    if not cand:
        return 0.0
    q_root = extract_root_domain(query_domain)
    c_root = extract_root_domain(cand)
    if q_root == c_root:
        return 1.0
    if query_domain in cand or cand in query_domain:
        return 0.85
    q_brand = q_root.split(".")[0]
    c_brand = c_root.split(".")[0]
    if q_brand and c_brand and q_brand == c_brand:
        return 0.60
    if difflib.SequenceMatcher(None, q_brand, c_brand).ratio() > 0.85:
        return 0.40
    return 0.0


# ══ CACHE ════════════════════════════════════════════════════

def _cache_key(identifier):
    return hashlib.md5(identifier.lower().encode()).hexdigest()

def _get_cached(key):
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        e = data.get(key)
        if e and time.time() - e.get("_cached_at", 0) < CACHE_TTL_S:
            return e
    except Exception:
        pass
    return None

def _set_cached(key, data):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        cache = {}
        if CACHE_FILE.exists():
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        data["_cached_at"] = time.time()
        cache[key] = data
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        _log(f"[Cache] Erreur : {e}")


# ══ SESSION HTTP ══════════════════════════════════════════════

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
})

def _get_with_backoff(url, params):
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, params=params, timeout=15)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 10)) + random.uniform(0, 3)
                _log(f"[Yahoo] Rate limit — attente {wait:.1f}s")
                time.sleep(wait)
                continue
            if r.status_code == 401:
                session.cookies.clear()
                time.sleep(2)
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError:
            time.sleep((2 ** attempt) + random.uniform(0, 1))
        except requests.exceptions.Timeout:
            time.sleep(2 ** attempt)
        except Exception as e:
            _log(f"[Yahoo] Erreur : {type(e).__name__}: {e}")
            return None
    return None

def _parse_quotes(data):
    if not data or not isinstance(data, dict):
        return []
    finance = data.get("finance", data)
    result  = finance.get("result")
    if isinstance(result, list) and result:
        return result[0].get("quotes") or []
    if isinstance(result, dict):
        return result.get("quotes") or []
    return data.get("quotes") or []

def _fetch_quotes(query, region="US"):
    params = {
        "q": query, "lang": "en-US", "region": region,
        "quotesCount": 10, "newsCount": 0,
        "enableFuzzyQuery": False, "enableCb": True,
    }
    _log(f"[Yahoo] Requête : {query!r} (region={region})")
    data = _get_with_backoff(YH_SEARCH_URL, params)
    if not data:
        return []
    quotes = _parse_quotes(data)
    _log(f"[Parser] {len(quotes)} quotes")
    return quotes


# ══ SCORING ══════════════════════════════════════════════════

def _name_score(query, candidate):
    q = _norm(_strip_legal(query))
    c = _norm(_strip_legal(candidate))
    if not q or not c: return 0.0
    if q == c: return 1.0
    if q in c or c in q: return 0.90
    seq = difflib.SequenceMatcher(None, q, c).ratio()
    tq, tc = set(q.split()), set(c.split())
    union = tq | tc
    jac = len(tq & tc) / len(union) if union else 0.0
    return round(0.6 * seq + 0.4 * jac, 4)

def _exchange_score(exchange, iso2):
    if not exchange or not iso2: return 0.3
    expected = COUNTRY_EXCHANGES.get(iso2.upper(), [])
    if not expected: return 0.3
    if exchange in expected: return 1.0
    if exchange in COUNTRY_EXCHANGES.get("US", []): return 0.5
    return 0.1

def _type_score(qt):
    return {"EQUITY": 1.0, "FUND": 0.5, "ETF": 0.2}.get((qt or "").upper(), 0.1)

def _compute_score(domain, company_name, iso2, quote, yf_website=""):
    ln = quote.get("longname") or quote.get("longName") or ""
    sn = quote.get("shortname") or quote.get("shortName") or ""
    name_s = max(_name_score(company_name, ln), _name_score(company_name, sn))
    exch_s = _exchange_score(quote.get("exchange") or "", iso2)
    type_s = _type_score(quote.get("quoteType") or "")
    dom_s  = domain_score(domain, yf_website) if yf_website else 0.0
    if dom_s > 0:
        # Domaine disponible → il prend le dessus (50%)
        return round(0.50 * dom_s + 0.30 * name_s + 0.15 * exch_s + 0.05 * type_s, 4)
    # Fallback scoring classique
    return round(0.55 * name_s + 0.30 * exch_s + 0.15 * type_s, 4)


# ══ ENRICHISSEMENT YFINANCE ═══════════════════════════════════

def _enrich(symbol):
    FIELDS = [
        "longName", "shortName", "sector", "industry",
        "country", "city", "website",
        "fullTimeEmployees", "marketCap", "currency",
        "totalRevenue", "ebitda", "netIncomeToCommon",
        "totalDebt", "totalCash",
        "grossMargins", "operatingMargins", "profitMargins",
        "revenueGrowth", "earningsGrowth",
        "debtToEquity", "returnOnEquity",
        "trailingPE", "forwardPE",
        "regularMarketPrice", "52WeekChange", "dividendYield",
        "recommendationKey", "numberOfAnalystOpinions",
        "longBusinessSummary",
    ]
    try:
        info   = yf.Ticker(symbol).info or {}
        result = {k: info[k] for k in FIELDS if k in info and info[k] is not None}
        for f in ("grossMargins", "operatingMargins", "profitMargins"):
            if f in result:
                result[f"{f}_pct"] = f"{result[f]*100:.1f}%"
        if "revenueGrowth" in result:
            sign = "+" if result["revenueGrowth"] >= 0 else ""
            result["revenueGrowth_pct"] = f"{sign}{result['revenueGrowth']*100:.1f}%"
        return result
    except Exception as e:
        _log(f"[yfinance] Erreur {symbol} : {e}")
        return {}


# ══ STRATÉGIE 1 — PAR DOMAINE ════════════════════════════════

def _match_by_domain(domain, company_name, iso2):
    _log(f"[Domaine] Recherche par domaine : {domain}")
    root   = extract_root_domain(domain)
    brand  = root.split(".")[0]
    region = iso2 or "US"

    candidates = {}
    for q in ([root, brand] if brand != root else [root]):
        for quote in _fetch_quotes(q, region):
            sym = quote.get("symbol")
            if not sym or sym in candidates:
                continue
            ln = quote.get("longname") or quote.get("longName") or ""
            sn = quote.get("shortname") or quote.get("shortName") or ""
            # Pré-filtrage : évite les enrichissements yfinance inutiles
            if max(_name_score(company_name or brand, ln),
                   _name_score(company_name or brand, sn)) < 0.20:
                continue
            candidates[sym] = quote
        time.sleep(random.uniform(0.3, 0.6))

    if not candidates:
        _log(f"[Domaine] Aucun candidat")
        return None

    _log(f"[Domaine] {len(candidates)} candidats → cross-validation website")

    best_score, best_data = -1.0, {}
    for sym, quote in candidates.items():
        yf_data    = _enrich(sym)
        yf_website = yf_data.get("website") or ""
        score      = _compute_score(domain, company_name or brand, iso2, quote, yf_website)
        _log(f"[Domaine]   {sym:12s} | website={yf_website:35s} | score={score:.2f}")
        if score > best_score:
            best_score = score
            best_data  = {**quote, **yf_data,
                          "_match_score": score, "_match_method": "domain"}

    if best_score < MIN_SCORE:
        _log(f"[Domaine] Score {best_score:.2f} insuffisant → fallback")
        return None
    return best_data


# ══ STRATÉGIE 2 — PAR NOM + PAYS (fallback) ══════════════════

def _match_by_name(company_name, iso2, country, address=""):
    _log(f"[Nom] Fallback nom+pays : {company_name} ({country})")
    city  = _extract_city(address, country)
    region = iso2 or "US"
    queries = [company_name]
    if city and _norm(city) not in _norm(company_name):
        queries.append(f"{company_name} {city}")
    if iso2 and iso2 not in company_name.upper():
        queries.append(f"{company_name} {iso2}")

    best_by_sym = {}
    for q in queries:
        for quote in _fetch_quotes(q, region):
            sym = quote.get("symbol")
            if not sym: continue
            ln = quote.get("longname") or quote.get("longName") or ""
            sn = quote.get("shortname") or quote.get("shortName") or ""
            name_s = max(_name_score(company_name, ln), _name_score(company_name, sn))
            exch_s = _exchange_score(quote.get("exchange") or "", iso2)
            type_s = _type_score(quote.get("quoteType") or "")
            score  = round(0.55 * name_s + 0.30 * exch_s + 0.15 * type_s, 4)
            quote["_match_score"]  = score
            quote["_match_method"] = "name_country"
            if score > best_by_sym.get(sym, {}).get("_match_score", -1):
                best_by_sym[sym] = quote
        time.sleep(random.uniform(0.3, 0.6))

    if not best_by_sym:
        return None
    best = max(best_by_sym.values(), key=lambda q: q["_match_score"])
    if best["_match_score"] < MIN_SCORE:
        return None
    return {**best, **_enrich(best["symbol"])}


def _extract_city(address, country):
    if not address: return ""
    c = _norm(country)
    if "," in address:
        for part in reversed([p.strip() for p in address.split(",")]):
            pn = _norm(part)
            if not pn or len(pn) < 3: continue
            if c and c in pn: continue
            if re.fullmatch(r"[\d\-\s]+", pn): continue
            return part
    words = address.split()
    tail  = " ".join(words[-5:])
    tail  = re.sub(rf"\b{re.escape(country.strip())}\b", "", tail, flags=re.I).strip()
    return tail if len(_norm(tail)) >= 3 else ""


# ══ FONCTION PRINCIPALE ═══════════════════════════════════════

def find_ticker(
    website_url:  str,
    company_name: str   = "",
    country:      str   = "",
    address:      str   = "",
    min_score:    float = MIN_SCORE,
) -> Optional[Dict]:
    """
    Matching Yahoo Finance par website_url (clé universelle).

    Args:
        website_url  : URL officielle ex: "https://www.capgemini.com"  ← ENTRÉE PRINCIPALE
        company_name : nom (confirme le match + sert de fallback)
        country      : pays en texte libre
        address      : adresse complète
        min_score    : seuil minimum [0.0–1.0]

    Returns:
        Dict avec symbol, website, sector, marketCap, profitMargins_pct,
               revenueGrowth_pct, debtToEquity, longBusinessSummary,
               _domain (clé de jointure), _match_score, _match_method
        None si aucun match
    """
    domain = extract_domain(website_url)
    if domain in GENERIC_DOMAINS:
        domain = ""

    iso2             = _iso2(country)
    cache_identifier = domain or f"{company_name.lower()}|{country.lower()}"
    cached           = _get_cached(_cache_key(cache_identifier))
    if cached:
        _log(f"[Cache] Hit : {cache_identifier}")
        return cached

    result = None

    # Stratégie 1 — domaine
    if domain:
        result = _match_by_domain(domain, company_name, iso2)

    # Stratégie 2 — fallback nom+pays
    if result is None and company_name:
        result = _match_by_name(company_name, iso2, country, address)

    if result is None:
        print(f"  → Aucun match : {website_url or company_name}")
        return None

    score = result.get("_match_score", 0)
    result["_match_level"] = (
        "excellent" if score >= 0.80 else "bon" if score >= 0.60 else "moyen"
    )
    result["_domain"]      = domain
    result["_website_url"] = website_url

    print(f"  {result.get('symbol'):12s} | "
          f"{(result.get('longName') or result.get('longname') or '')[:30]:30s} | "
          f"score {score:.2f} ({result['_match_method']}) | {result.get('exchange')}")

    _set_cached(_cache_key(cache_identifier), result)
    return result


# ══ MAIN ══════════════════════════════════════════════════════

if __name__ == "__main__":
    exemples = [
    {"website_url": "https://www.philapharma.com",    "company_name": "Philadelphia Pharmaceuticals",        "country": "Jordan"}
]

    for ex in exemples:
        print(f"\n{'='*65}")
        print(f"URL     : {ex['website_url']}")
        print(f"Domaine : {extract_domain(ex['website_url'])}")
        result = find_ticker(**ex)
        if result:
            mc = result.get("marketCap")
            print(f"  Ticker      : {result.get('symbol')}")
            print(f"  Domaine clé : {result.get('_domain')}")
            print(f"  Méthode     : {result.get('_match_method')}")
            print(f"  Score       : {result.get('_match_score'):.2f} — {result.get('_match_level')}")
            print(f"  Secteur     : {result.get('sector')} / {result.get('industry')}")
            print(f"  Employés    : {result.get('fullTimeEmployees')}")
            if mc: print(f"  Mkt Cap     : {mc/1e9:.1f} Md$")
            if result.get("revenueGrowth_pct"): print(f"  Croiss. CA  : {result.get('revenueGrowth_pct')}")
            if result.get("profitMargins_pct"): print(f"  Marge nette : {result.get('profitMargins_pct')}")
            if result.get("debtToEquity"):      print(f"  Dette/CP    : {result.get('debtToEquity'):.1f}x")
            if result.get("recommendationKey"): print(f"  Analystes   : {result.get('recommendationKey')}")
            s = result.get("longBusinessSummary", "")
            if s: print(f"  Description : {s[:120]}…")