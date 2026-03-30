import json
from playwright.async_api import async_playwright
from config import EMAIL, PASSWORD, SESSION_FILE
from utils import human_delay

try:
    from playwright_stealth import Stealth
    STEALTH_MODE = "new"
except ImportError:
    try:
        from playwright_stealth import stealth_async
        STEALTH_MODE = "old"
    except ImportError:
        STEALTH_MODE = "none"
        print("⚠️  playwright-stealth non disponible.")


async def apply_stealth(page):
    if STEALTH_MODE == "new":
        await Stealth().apply_stealth_async(page)
    elif STEALTH_MODE == "old":
        await stealth_async(page)


async def create_browser(playwright):
    browser = await playwright.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
    )
    return browser, context


async def login(page):
    print("🔐 Connexion à LinkedIn...")
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    await human_delay()
    await page.fill("#username", EMAIL)
    await human_delay(300, 700)
    await page.fill("#password", PASSWORD)
    await human_delay(500, 1000)
    await page.click('[type="submit"]')
    await page.wait_for_url("**/feed/**", timeout=15000)
    print("✅ Connecté !")


async def save_session(context):
    cookies = await context.cookies()
    SESSION_FILE.write_text(json.dumps(cookies))
    print(f"💾 Session sauvegardée → {SESSION_FILE}")


async def load_session(context):
    if SESSION_FILE.exists():
        cookies = json.loads(SESSION_FILE.read_text())
        await context.add_cookies(cookies)
        print("♻️  Session chargée.")
        return True
    return False


async def ensure_logged_in(page, context):
    session_loaded = await load_session(context)
    if not session_loaded:
        await login(page)
        await save_session(context)
    else:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await human_delay(1500, 2500)
        if "login" in page.url:
            print("⚠️  Session expirée, reconnexion...")
            await login(page)
            await save_session(context)