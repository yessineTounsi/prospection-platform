import certifi
import urllib3
import random
import requests
import cloudscraper
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from playwright.sync_api import sync_playwright

from config import REQUEST_TIMEOUT, session, cloud_session
from utils import get_browser_headers, random_delay

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from playwright_stealth import stealth_sync
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False


# ─────────────────────────────────────────────
#  USER AGENTS ROTATIFS
# ─────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def _random_headers() -> dict:
    ua = random.choice(_USER_AGENTS)
    return {
        "User-Agent":                ua,
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language":           "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding":           "gzip, deflate, br",
        "Cache-Control":             "no-cache",
        "Pragma":                    "no-cache",
        "Sec-Fetch-Dest":            "document",
        "Sec-Fetch-Mode":            "navigate",
        "Sec-Fetch-Site":            "none",
        "Sec-Fetch-User":            "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection":                "keep-alive",
    }


# ─────────────────────────────────────────────
#  DÉTECTION SITE JS
# ─────────────────────────────────────────────

def _is_js_rendered_site(html: str) -> bool:
    """Détecte si une page nécessite JS pour afficher son contenu."""
    if not html or len(html) < 500:
        return True

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    body = soup.find("body")
    if not body:
        return True

    visible_text = body.get_text(separator=" ", strip=True)
    html_size    = len(html)
    text_size    = len(visible_text)

    if text_size < 200:
        return True
    if html_size > 10000 and (text_size / html_size) < 0.03:
        return True

    js_roots = [{"id": "root"}, {"id": "app"}, {"id": "__next"},
                {"id": "gatsby-focus-wrapper"}, {"data-reactroot": True}]
    for attrs in js_roots:
        root = soup.find(True, attrs)
        if root and len(root.get_text(strip=True)) < 100:
            return True

    js_markers = ["__NEXT_DATA__", "__NUXT__", "data-wf-site",
                  "data-reactroot", "ng-version", "data-vue-app"]
    for marker in js_markers:
        if marker in html and text_size < 500:
            return True

    return False


# ─────────────────────────────────────────────
#  FETCH DYNAMIQUE — PLAYWRIGHT STEALTH
# ─────────────────────────────────────────────

def fetch_page_dynamic(url: str, wait_seconds: int = 4) -> str:
    """Rendu JS via Playwright avec stealth complet."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--allow-running-insecure-content",
            ],
        )
        ua = random.choice(_USER_AGENTS)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=ua,
            locale="fr-FR",
            timezone_id="Europe/Paris",
            extra_http_headers={
                "Accept-Language":           "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept":                    "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Encoding":           "gzip, deflate, br",
                "Cache-Control":             "no-cache",
                "Sec-Fetch-Dest":            "document",
                "Sec-Fetch-Mode":            "navigate",
                "Sec-Fetch-Site":            "none",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        # Scripts stealth
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['fr-FR','fr','en']});
            window.chrome = {runtime: {}};
        """)

        if _STEALTH_AVAILABLE:
            pass  # appliqué sur la page

        page = context.new_page()

        if _STEALTH_AVAILABLE:
            stealth_sync(page)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Simule un vrai utilisateur
            page.mouse.move(random.randint(100, 800), random.randint(100, 600))
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            page.wait_for_timeout(wait_seconds * 1000)
            html = page.content()
        finally:
            browser.close()

    return html


# ─────────────────────────────────────────────
#  FETCH STATIQUE — MULTI-STRATÉGIES
# ─────────────────────────────────────────────

def _fetch_static(url: str) -> str:
    """
    4 stratégies statiques dans l'ordre :
    1. requests avec headers aléatoires
    2. requests sans vérification SSL
    3. cloudscraper Chrome
    4. cloudscraper Firefox
    """
    headers = _random_headers()

    # ── 1. requests sans vérification SSL (contourne les erreurs SSL)
    try:
        r = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass

    # ── 2. requests avec SSL standard
    try:
        r = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT,
                       verify=certifi.where())
        if r.status_code == 200:
            return r.text
    except Exception:
        pass

    # ── 3. cloudscraper Chrome
    try:
        scraper = cloudscraper.create_scraper(browser={"browser": "chrome",
                                                        "platform": "windows",
                                                        "mobile": False})
        r = scraper.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass

    # ── 4. cloudscraper Firefox
    try:
        scraper = cloudscraper.create_scraper(browser={"browser": "firefox",
                                                        "platform": "windows",
                                                        "mobile": False})
        r = scraper.get(url, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass

    raise RuntimeError(f"Statique échoué pour {url}")


# ─────────────────────────────────────────────
#  FETCH PRINCIPAL — UNIVERSEL
# ─────────────────────────────────────────────

def fetch_page(url: str, use_dynamic_fallback: bool = False) -> str:
    """
    Fetch universel avec 5 niveaux de fallback :
    1. requests (headers aléatoires)
    2. requests (sans SSL)
    3. cloudscraper Chrome
    4. cloudscraper Firefox
    5. Playwright stealth (si JS détecté ou use_dynamic_fallback)
    """
    random_delay()

    html = None

    # ── Tentative statique (4 stratégies)
    try:
        html = _fetch_static(url)
    except Exception:
        pass

    # ── Vérifie si Playwright est nécessaire
    needs_playwright = (
        use_dynamic_fallback or
        html is None or
        _is_js_rendered_site(html)
    )

    if needs_playwright:
        try:
            html = fetch_page_dynamic(url)
            return html
        except Exception:
            if html is not None:
                return html  # retourne le statique en dernier recours
            raise RuntimeError(f"Impossible de récupérer {url} après tous les fallbacks")

    return html