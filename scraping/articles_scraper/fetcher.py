import certifi
import urllib3
import requests
from playwright.sync_api import sync_playwright

from config import REQUEST_TIMEOUT, session, cloud_session
from utils import get_browser_headers, random_delay

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Passer à False si le site utilise Cloudflare Turnstile (challenge visuel)
HEADLESS_MODE = True

# ── Import optionnel de playwright-stealth (pip install playwright-stealth)
try:
    from playwright_stealth import stealth_sync
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False


# ─────────────────────────────────────────────
#  FETCH DYNAMIQUE (Playwright + stealth)
# ─────────────────────────────────────────────

def fetch_page_dynamic(url: str, wait_seconds: int = 5) -> str:
    """
    Rendu JavaScript via Playwright avec stealth.
    Si HEADLESS_MODE = False → ouvre une vraie fenêtre Chrome,
    permettant de passer manuellement les challenges Cloudflare.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS_MODE,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Europe/Paris",
            extra_http_headers={
                "Accept-Language":           "en-US,en;q=0.9,fr;q=0.8",
                "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding":           "gzip, deflate, br",
                "Cache-Control":             "no-cache",
                "Sec-Fetch-Dest":            "document",
                "Sec-Fetch-Mode":            "navigate",
                "Sec-Fetch-Site":            "none",
                "Sec-Fetch-User":            "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        page = context.new_page()

        # Applique playwright-stealth si disponible
        if _STEALTH_AVAILABLE:
            stealth_sync(page)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Si mode non-headless : attend que l'utilisateur passe le challenge
            if not HEADLESS_MODE:
                print(f"[BROWSER] Résous le challenge Cloudflare dans la fenêtre, puis attends...")
                page.wait_for_timeout(15000)  # 15s pour résoudre manuellement
            else:
                # Scroll simulé pour déclencher le lazy-load JS
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(wait_seconds * 1000)

            html = page.content()
        finally:
            browser.close()

    return html


# ─────────────────────────────────────────────
#  FETCH STATIQUE (requests + cloudscraper)
# ─────────────────────────────────────────────

def fetch_page(url: str, use_dynamic_fallback: bool = False) -> str:
    """
    Fetch robuste avec 3 niveaux de fallback :
      1. requests standard
      2. cloudscraper (anti-bot simple)
      3. Playwright stealth (Cloudflare / JS avancé)
         — uniquement si use_dynamic_fallback=True
    """
    random_delay()
    headers = get_browser_headers()

    def _try_requests(verify=True):
        r = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=verify)
        r.raise_for_status()
        return r.text

    def _try_cloudscraper():
        r = cloud_session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        r.raise_for_status()
        return r.text

    # Niveau 1 — requests standard
    try:
        return _try_requests(verify=certifi.where())
    except requests.exceptions.SSLError:
        try:
            return _try_requests(verify=False)
        except Exception:
            pass
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status not in [403, 406, 429, 503]:
            raise
    except Exception:
        pass

    # Niveau 2 — cloudscraper
    try:
        return _try_cloudscraper()
    except Exception:
        pass

    # Niveau 3 — Playwright stealth
    if use_dynamic_fallback:
        try:
            return fetch_page_dynamic(url)
        except Exception:
            pass

    raise RuntimeError(f"Impossible de récupérer {url} après tous les fallbacks")