"""
╔══════════════════════════════════════════════════════════════════════╗
║   SITE TECH EXTRACTOR  — Powered by Wappalyzer OSS (3920 techs)     ║
║   E-Commerce Intelligence · Intelligent Discovery Platform           ║
╚══════════════════════════════════════════════════════════════════════╝

• 3 450+ technologies détectables (88% coverage Wappalyzer)
• Zero re-fetch — analyse sur HTML déjà scraped
• Zero faux positifs DOM (DOM matching désactivé, nécessite Playwright)
• Cache local automatique (téléchargement npm unique)
• Scoring e-commerce custom (0-100%)

USAGE:
    from tech_extractor import TechExtractor

    result  = TechExtractor.analyze(html=page_html, url=site_url)
    results = TechExtractor.analyze_batch([{html, url, headers?, cookies?}, ...])
"""

from __future__ import annotations

import io
import json
import logging
import re
import tarfile
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─────────────────────────── Config ────────────────────────────────────

WAPPALYZER_VERSION = "6.10.66"
CACHE_FILE         = Path(__file__).parent / "wappalyzer_cache.json"
NPM_META_URL       = f"https://registry.npmjs.org/wappalyzer/{WAPPALYZER_VERSION}"

# Seuil de confiance minimum pour accepter un match (0-1)
MIN_CONFIDENCE = 0.5

# Technologies connues comme faux positifs systématiques (bruit Wappalyzer)
TECH_BLACKLIST: set[str] = {
    "@sulu/web",
    "Docusaurus",
    "HeadJS",
    "jQuery DevBridge Autocomplete",
    "jQuery-pjax",
    "jQuery Migrate",
    "Moment.js",
}

# ─────────────────────────── Category mapping ──────────────────────────

# Wappalyzer cat id → champ TechStack
CATEGORY_MAP: dict[int, str] = {
    6:   "platform",           # Ecommerce
    108: "platform",           # Ecommerce frontends
    1:   "cms",                # CMS
    11:  "cms",                # Blogs
    51:  "cms",                # Page builders
    12:  "frontend_framework", # JS frameworks
    18:  "frontend_framework", # Web frameworks
    26:  "frontend_framework", # Mobile frameworks
    57:  "frontend_framework", # Static site generators
    59:  "js_libraries",       # JS libraries
    66:  "css_framework",      # UI frameworks
    10:  "analytics",          # Analytics
    74:  "analytics",          # A/B Testing
    78:  "analytics",          # RUM
    83:  "analytics",          # Browser fingerprinting
    42:  "tag_managers",       # Tag managers
    36:  "advertising",        # Advertising
    77:  "advertising",        # Retargeting
    71:  "advertising",        # Affiliate
    94:  "advertising",        # Referral marketing
    32:  "crm_marketing",      # Marketing automation
    53:  "crm_marketing",      # CRM
    75:  "crm_marketing",      # Email
    76:  "crm_marketing",      # Personalisation
    86:  "crm_marketing",      # Segmentation
    97:  "crm_marketing",      # CDP
    98:  "crm_marketing",      # Cart abandonment
    41:  "payment_gateways",   # Payment processors
    91:  "payment_gateways",   # Buy now pay later
    90:  "review_platform",    # Reviews
    84:  "review_platform",    # Loyalty & rewards
    52:  "live_chat",          # Live chat
    58:  "live_chat",          # User onboarding
    29:  "search_engines",     # Search engines
    31:  "cdn",                # CDN
    88:  "hosting",            # Hosting
    62:  "hosting",            # PaaS
    63:  "hosting",            # IaaS
    22:  "server",             # Web servers
    64:  "server",             # Reverse proxies
    65:  "server",             # Load balancers
    23:  "caching",            # Caching
    16:  "security",           # Security
    67:  "security",           # Cookie compliance
    69:  "security",           # Authentication
    70:  "security",           # SSL/TLS
    99:  "shipping",           # Shipping carriers
    107: "shipping",           # Fulfilment
    102: "shipping",           # Returns
    73:  "other",              # Surveys
    72:  "other",              # Appointment scheduling
    89:  "other",              # Translation
    110: "other",              # Form builders
}

# Cat ids qui indiquent un site e-commerce (pour le scoring)
ECOMMERCE_CAT_IDS = {6, 41, 91, 98, 99, 100, 102, 106, 107, 108}

# Signaux HTML custom (en plus de Wappalyzer) pour le scoring e-commerce
ECOMMERCE_SIGNALS_HTML = [
    (r'"@type":\s*"Product"',           20, "schema:Product"),
    (r'"@type":\s*"Offer"',             15, "schema:Offer"),
    (r'"@type":\s*"ItemList"',          10, "schema:ItemList"),
    (r'add[_-]to[_-]cart',             10, "pattern:add-to-cart"),
    (r'data-product-id|product[_-]id',  8, "pattern:product-id"),
    (r'/cart\b|/checkout\b',            8, "pattern:cart-url"),
    (r'"sku"\s*:',                       6, "pattern:sku"),
    (r'"price"\s*:\s*[\d"]',            6, "pattern:price"),
    (r'type=["\']number["\'].*quantit', 5, "pattern:quantity-input"),
    (r'free.shipping|livraison.gratuite',4, "pattern:free-shipping"),
    (r'in.stock|out.of.stock|en.stock', 4, "pattern:stock"),
]


# ─────────────────────────── Data model ────────────────────────────────

@dataclass
class TechStack:
    url: str = ""
    domain: str = ""
    is_ecommerce: bool = False
    ecommerce_confidence: float = 0.0
    ecommerce_signals: list[str] = field(default_factory=list)

    platform:           list[str] = field(default_factory=list)
    cms:                list[str] = field(default_factory=list)
    frontend_framework: list[str] = field(default_factory=list)
    js_libraries:       list[str] = field(default_factory=list)
    css_framework:      list[str] = field(default_factory=list)
    analytics:          list[str] = field(default_factory=list)
    tag_managers:       list[str] = field(default_factory=list)
    advertising:        list[str] = field(default_factory=list)
    crm_marketing:      list[str] = field(default_factory=list)
    payment_gateways:   list[str] = field(default_factory=list)
    review_platform:    list[str] = field(default_factory=list)
    live_chat:          list[str] = field(default_factory=list)
    search_engines:     list[str] = field(default_factory=list)
    shipping:           list[str] = field(default_factory=list)
    cdn:                list[str] = field(default_factory=list)
    hosting:            list[str] = field(default_factory=list)
    server:             list[str] = field(default_factory=list)
    caching:            list[str] = field(default_factory=list)
    security:           list[str] = field(default_factory=list)
    other:              list[str] = field(default_factory=list)

    # Toutes les techs détectées : {name → version | ""}
    all_technologies: dict[str, str] = field(default_factory=dict)

    technologies_count: int   = 0
    scan_duration_ms:   float = 0.0
    error: Optional[str]      = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["technologies_count"] = len(self.all_technologies)
        return d


# ─────────────────────────── Wappalyzer DB ─────────────────────────────

class WappalyzerDB:
    """
    Charge les fingerprints Wappalyzer depuis le cache local.
    Si le cache est absent, télécharge depuis npm (une seule fois).
    """
    _instance: Optional["WappalyzerDB"] = None

    def __init__(self, technologies: dict, categories: dict):
        self.technologies = technologies
        self.categories   = categories

    @classmethod
    def load(cls, cache_path: Path = CACHE_FILE) -> "WappalyzerDB":
        if cls._instance:
            return cls._instance

        if cache_path.exists():
            logger.info(f"[WappalyzerDB] Cache trouvé : {cache_path}")
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            logger.info("[WappalyzerDB] Téléchargement depuis npm...")
            data = cls._download_from_npm()
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info(f"[WappalyzerDB] Cache sauvegardé : {cache_path}")

        cls._instance = cls(data["technologies"], data.get("categories", {}))
        logger.info(f"[WappalyzerDB] {len(cls._instance.technologies)} technologies chargées")
        return cls._instance

    @classmethod
    def reset(cls):
        """Force re-téléchargement (utile pour mise à jour)."""
        cls._instance = None
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()

    @staticmethod
    def _download_from_npm() -> dict:
        req = urllib.request.Request(NPM_META_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            meta = json.loads(r.read())
        tarball_url = meta["dist"]["tarball"]

        req2 = urllib.request.Request(tarball_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=60) as r:
            raw = r.read()

        all_techs, categories = {}, {}
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            for member in tar.getmembers():
                f = tar.extractfile(member)
                if not f:
                    continue
                if "technologies" in member.name and member.name.endswith(".json"):
                    all_techs.update(json.loads(f.read()))
                elif "categories.json" in member.name:
                    categories = json.loads(f.read())

        return {"technologies": all_techs, "categories": categories,
                "version": WAPPALYZER_VERSION}


# ─────────────────────────── Pattern helpers ───────────────────────────

def _parse_pattern(raw) -> tuple[re.Pattern | None, str, float]:
    """
    Parse un pattern Wappalyzer : "regex\\;version:\\1\\;confidence:75"
    Retourne (compiled_regex, version_template, confidence 0-1)
    """
    if not isinstance(raw, str):
        raw = " ".join(raw) if isinstance(raw, list) else str(raw or "")

    parts      = raw.split("\\;")
    regex_str  = parts[0]
    version    = ""
    confidence = 1.0

    for part in parts[1:]:
        if part.startswith("version:"):
            version = part[8:]
        elif part.startswith("confidence:"):
            try:
                confidence = int(part[11:]) / 100
            except ValueError:
                pass

    if not regex_str.strip():
        return None, version, confidence

    try:
        return re.compile(regex_str, re.IGNORECASE), version, confidence
    except re.error:
        try:
            return re.compile(re.escape(regex_str), re.IGNORECASE), version, confidence
        except Exception:
            return None, version, confidence


def _extract_version(match: re.Match, tpl: str) -> str:
    if not tpl or not match:
        return ""
    result = tpl
    try:
        for i, g in enumerate(match.groups(), 1):
            result = result.replace(f"\\{i}", g or "")
    except Exception:
        pass
    return result.strip(" \\").strip()


def _to_list(v) -> list:
    if isinstance(v, list): return v
    if v is not None:       return [v]
    return []


# ─────────────────────────── Core engine ───────────────────────────────

class TechExtractor:
    """
    Analyse statique du stack technique à partir de HTML brut.
    Aucun réseau requis — s'intègre directement dans ton pipeline scraping.
    """
    _db: Optional[WappalyzerDB] = None

    @classmethod
    def _get_db(cls) -> WappalyzerDB:
        if cls._db is None:
            cls._db = WappalyzerDB.load()
        return cls._db

    # ── Public API ────────────────────────────────────────────────────

    @classmethod
    def analyze(
        cls,
        html: str,
        url: str = "",
        headers: dict | None = None,
        cookies: dict | None = None,
    ) -> TechStack:
        """
        Analyse un HTML déjà scraped.

        Args:
            html    : HTML brut de la page
            url     : URL du site (optionnel — pour domaine + SSL)
            headers : headers HTTP de la réponse scraper (dict, optionnel)
            cookies : cookies de la réponse scraper (dict, optionnel)

        Returns:
            TechStack
        """
        t0  = time.perf_counter()
        db  = cls._get_db()
        stack = TechStack(url=url)

        # Domaine + SSL depuis l'URL
        if url:
            from urllib.parse import urlparse
            p = urlparse(url if "://" in url else f"https://{url}")
            stack.domain = p.netloc or url
            stack.ssl    = p.scheme == "https"

        if not html or not html.strip():
            stack.error = "empty HTML"
            stack.scan_duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            return stack

        # Normalisation des inputs
        h  = {k.lower(): str(v) for k, v in (headers or {}).items()}
        ck = {k.lower(): str(v) for k, v in (cookies or {}).items()}

        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        html_lower  = html.lower()
        script_srcs    = [s.get("src", "") for s in soup.find_all("script") if s.get("src")]
        inline_scripts = [s.get_text() for s in soup.find_all("script")
                          if not s.get("src") and s.get_text(strip=True)]
        meta_tags   = {
            (m.get("name") or m.get("property") or "").lower(): m.get("content", "")
            for m in soup.find_all("meta")
        }

        # ── Fingerprinting loop ───────────────────────────────────────
        detected: dict[str, tuple[float, str]] = {}  # name → (confidence, version)

        for tech_name, fp in db.technologies.items():
            if tech_name in TECH_BLACKLIST:
                continue
            conf, ver = cls._match(fp, html, html_lower, script_srcs, inline_scripts, h, ck, meta_tags)
            if conf >= MIN_CONFIDENCE:
                prev_conf, prev_ver = detected.get(tech_name, (0, ""))
                if conf > prev_conf:
                    detected[tech_name] = (conf, ver or prev_ver)

        # ── Résolution des "implies" (dépendances) ────────────────────
        implied = {}
        for tech_name in list(detected):
            fp = db.technologies.get(tech_name, {})
            for imp in _to_list(fp.get("implies")):
                imp_name = imp.split("\\;")[0]
                if imp_name in db.technologies and imp_name not in detected:
                    implied[imp_name] = (0.75, "")

        detected.update({k: v for k, v in implied.items() if k not in detected})

        # ── Populate TechStack ────────────────────────────────────────
        for tech_name, (conf, ver) in detected.items():
            fp   = db.technologies.get(tech_name, {})
            cats = fp.get("cats", [])
            stack.all_technologies[tech_name] = ver

            assigned = False
            for cat_id in cats:
                field_name = CATEGORY_MAP.get(cat_id)
                if field_name:
                    lst = getattr(stack, field_name, None)
                    if isinstance(lst, list) and tech_name not in lst:
                        lst.append(tech_name)
                    assigned = True
                    break  # une seule catégorie principale

        # ── E-commerce classification ─────────────────────────────────
        cls._classify_ecommerce(stack, db, detected, html, html_lower)

        stack.technologies_count = len(stack.all_technologies)
        stack.scan_duration_ms   = round((time.perf_counter() - t0) * 1000, 2)
        return stack

    @classmethod
    def analyze_batch(cls, records: list[dict]) -> list[TechStack]:
        """
        Analyse un batch de records.
        Chaque record : {html, url?, headers?, cookies?}

        Pour du parallélisme sur gros volumes :
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as ex:
                results = list(ex.map(lambda r: TechExtractor.analyze(**r), records))
        """
        return [
            cls.analyze(
                html    = r.get("html", ""),
                url     = r.get("url", ""),
                headers = r.get("headers"),
                cookies = r.get("cookies"),
            )
            for r in records
        ]

    # ── Matching engine ───────────────────────────────────────────────

    @classmethod
    def _match(
        cls, fp: dict,
        html: str, html_lower: str,
        script_srcs: list[str],
        inline_scripts: list[str],
        headers: dict, cookies: dict,
        meta: dict,
    ) -> tuple[float, str]:
        """
        Teste tous les signaux d'un fingerprint.
        Retourne (best_confidence, version_string).

        Signaux utilisés (du plus au moins fiable) :
          1. scriptSrc  — URL des scripts <script src="...">
          2. html       — regex dans le HTML brut
          3. headers    — headers HTTP de la réponse
          4. cookies    — cookies de la réponse
          5. meta       — balises <meta>
          6. js         — noms de variables JS dans le HTML
        """
        best_conf = 0.0
        best_ver  = ""

        def _update(conf: float, ver: str = ""):
            nonlocal best_conf, best_ver
            if conf > best_conf:
                best_conf = conf
                if ver:
                    best_ver = ver

        # 1. scriptSrc (signal le plus fiable — URL exacte du script)
        for raw in _to_list(fp.get("scriptSrc")):
            rx, ver_tpl, conf = _parse_pattern(raw)
            if rx is None:
                continue
            for src in script_srcs:
                m = rx.search(src)
                if m:
                    _update(conf, _extract_version(m, ver_tpl))
                    break

        # Early exit si déjà haute confiance
        if best_conf >= 0.9:
            return best_conf, best_ver

        # 2. html (regex dans le HTML brut)
        for raw in _to_list(fp.get("html")):
            rx, ver_tpl, conf = _parse_pattern(raw)
            if rx is None:
                continue
            target = html if any(c.isupper() for c in raw.split("\\;")[0]) else html_lower
            m = rx.search(target)
            if m:
                _update(conf, _extract_version(m, ver_tpl))

        # 3. headers
        for hdr_key, raw in (fp.get("headers") or {}).items():
            rx, ver_tpl, conf = _parse_pattern(raw)
            val = headers.get(hdr_key.lower(), "")
            if not val:
                continue
            if rx is None:
                _update(conf)
            else:
                m = rx.search(val)
                if m:
                    _update(conf, _extract_version(m, ver_tpl))

        # 4. cookies
        for ck_key, raw in (fp.get("cookies") or {}).items():
            rx, ver_tpl, conf = _parse_pattern(raw)
            val = cookies.get(ck_key.lower(), "")
            if not val and ck_key.lower() not in cookies:
                continue
            if rx is None or not raw.strip():
                _update(conf if conf > 0 else 0.75)
            else:
                m = rx.search(val)
                if m:
                    _update(conf, _extract_version(m, ver_tpl))

        # 5. meta tags
        for meta_key, raw in (fp.get("meta") or {}).items():
            rx, ver_tpl, conf = _parse_pattern(raw)
            val = meta.get(meta_key.lower(), "")
            if not val:
                continue
            if rx is None:
                _update(conf)
            else:
                m = rx.search(val)
                if m:
                    _update(conf, _extract_version(m, ver_tpl))

        # 6. js globals — recherche dans les scripts inline uniquement
        #    (jamais sur le HTML complet : risque de faux positifs sur versions)
        if fp.get("js") and inline_scripts:
            for js_var, raw in fp["js"].items():
                root = js_var.split(".")[0]
                if not root or len(root) < 3:
                    continue
                rx, ver_tpl, conf = _parse_pattern(raw)
                found = False
                for script_text in inline_scripts:
                    if re.search(r'\b' + re.escape(root) + r'\b', script_text):
                        if rx is not None and not re.search(r'^\(?\.\*\)\??\$?', rx.pattern):
                            # Pattern spécifique (pas juste "capture tout")
                            m = rx.search(script_text)
                            if m:
                                _update(conf * 0.85, _extract_version(m, ver_tpl))
                                found = True
                                break
                        else:
                            # Pattern trop générique -> présence seulement, pas de version
                            _update(min(conf, 0.65))
                            found = True
                            break

        # DOM : désactivé volontairement
        # Raison : matching CSS selector sur HTML brut → faux positifs massifs
        # Solution si nécessaire : Playwright + page.query_selector()

        return best_conf, best_ver

    # ── E-Commerce classification ─────────────────────────────────────

    @classmethod
    def _classify_ecommerce(
        cls,
        stack: TechStack,
        db: WappalyzerDB,
        detected: dict[str, tuple[float, str]],
        html: str,
        html_lower: str,
    ):
        score   = 0.0
        signals = []

        # Signal A — technologies dans les catégories e-commerce
        for tech_name, (conf, _) in detected.items():
            fp   = db.technologies.get(tech_name, {})
            cats = set(fp.get("cats", []))
            hit  = cats & ECOMMERCE_CAT_IDS
            if not hit:
                continue
            cat_id = next(iter(hit))
            weight = (
                30 if cat_id == 6   else   # plateforme e-commerce
                20 if cat_id == 41  else   # paiement
                15 if cat_id == 91  else   # BNPL
                12                         # shipping, cart abandonment…
            )
            score += weight * conf
            signals.append(f"{tech_name} [cat:{cat_id}]")

        # Signal B — patterns HTML structurels + Schema.org
        for pat, pts, label in ECOMMERCE_SIGNALS_HTML:
            if re.search(pat, html if pat[0] == '"' else html_lower, re.IGNORECASE):
                score += pts
                signals.append(label)

        stack.ecommerce_confidence = round(min(score, 100), 1)
        stack.ecommerce_signals    = signals[:12]
        stack.is_ecommerce         = stack.ecommerce_confidence >= 15


# ─────────────────────────── Pretty printer ────────────────────────────

RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
CYAN = "\033[96m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
MAGENTA = "\033[95m"; RED = "\033[91m"; BLUE = "\033[94m"

def _c(t, col): return f"{col}{t}{RESET}"


class PrettyPrinter:

    SECTIONS = [
        ("Platform / E-commerce",  "platform",           CYAN),
        ("CMS",                    "cms",                 CYAN),
        ("Frontend Framework",     "frontend_framework",  CYAN),
        ("JS Libraries",           "js_libraries",        BLUE),
        ("CSS Framework",          "css_framework",       BLUE),
        ("CDN",                    "cdn",                 BLUE),
        ("Hosting",                "hosting",             BLUE),
        ("Server",                 "server",              BLUE),
        ("Caching",                "caching",             BLUE),
        ("Analytics",              "analytics",           GREEN),
        ("Tag Managers",           "tag_managers",        GREEN),
        ("Advertising",            "advertising",         YELLOW),
        ("CRM / Marketing",        "crm_marketing",       YELLOW),
        ("Payment Gateways",       "payment_gateways",    MAGENTA),
        ("Review Platforms",       "review_platform",     MAGENTA),
        ("Live Chat / Support",    "live_chat",           MAGENTA),
        ("Search",                 "search_engines",      MAGENTA),
        ("Shipping / Fulfilment",  "shipping",            MAGENTA),
        ("Security",               "security",            RED),
        ("Other",                  "other",               DIM),
    ]

    @classmethod
    def print_stack(cls, stack: TechStack, ecommerce_only: bool = True):
        if stack.error:
            print(_c(f"\n  ✗  {stack.domain or stack.url}: {stack.error}", RED))
            return

        badge = _c("✔ E-COMMERCE", GREEN) if stack.is_ecommerce else _c("✘ NOT E-COMMERCE", YELLOW)
        conf  = _c(f"({stack.ecommerce_confidence}%)", DIM)

        print()
        print(_c("━" * 66, CYAN))
        print(_c(f"  {stack.domain or stack.url}", BOLD + CYAN))
        print(f"  {badge}  {conf}")
        if stack.ecommerce_signals:
            print(_c(f"  Signals: {', '.join(stack.ecommerce_signals[:4])}", DIM))
        print(_c("━" * 66, CYAN))

        if ecommerce_only and not stack.is_ecommerce:
            print(_c("  ⚑  Non classifié e-commerce — analyse ignorée\n", YELLOW))
            return

        for title, field_name, col in cls.SECTIONS:
            items = getattr(stack, field_name, [])
            if not items:
                continue
            print(_c(f"\n  ▸ {title}", col + BOLD))
            for name in items:
                ver   = stack.all_technologies.get(name, "")
                label = f"{name}  {_c(ver, DIM)}" if ver else name
                print(f"    • {label}")

        n = len(stack.all_technologies)
        print()
        print(_c(f"  Total : {n} technologies  |  Scan : {stack.scan_duration_ms}ms", DIM))
        print(_c("━" * 66, CYAN))

    @classmethod
    def print_all(cls, stack: TechStack):
        """Liste toutes les techs détectées avec version."""
        print(_c(f"\n  All technologies — {stack.domain}", BOLD))
        for name in sorted(stack.all_technologies):
            ver = stack.all_technologies[name]
            print(f"    • {name}" + (_c(f"  v{ver}", DIM) if ver else ""))


# ─────────────────────────── CLI ───────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if len(sys.argv) < 2:
        print("Usage: python tech_extractor.py <file.html> [https://url.com] [--json] [--all] [--no-ecom-filter]")
        sys.exit(0)

    path      = sys.argv[1]
    url       = next((a for a in sys.argv[2:] if a.startswith("http")), "")
    as_json   = "--json"            in sys.argv
    show_all  = "--all"             in sys.argv
    no_filter = "--no-ecom-filter"  in sys.argv

    with open(path, encoding="utf-8", errors="ignore") as f:
        html = f.read()

    stack = TechExtractor.analyze(html=html, url=url)

    if as_json:
        print(json.dumps(stack.to_dict(), indent=2, ensure_ascii=False))
    else:
        PrettyPrinter.print_stack(stack, ecommerce_only=not no_filter)
        if show_all:
            PrettyPrinter.print_all(stack)

    # ── Sauvegarde JSON automatique dans stackoutput/ ─────────────────────
    output_dir = Path(__file__).parent / "stackoutput"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Nom du fichier = nom de domaine nettoyé (ex: www_cyrillus_fr.json)
    site_name = (stack.domain or Path(path).stem).replace(".", "_").replace("/", "_").replace(":", "")
    output_path = output_dir / f"{site_name}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stack.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"\n  ✔ JSON sauvegardé : {output_path}")