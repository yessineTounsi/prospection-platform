"""
LinkedIn Company Scraper - Mode Interactif
==========================================
Tape le nom de l'entreprise dans le terminal et le script scrape automatiquement.

Installation :
    python -m pip install playwright setuptools
    python -m pip uninstall playwright-stealth -y
    python -m pip install playwright-stealth
    playwright install chromium
"""

import asyncio
import random
import json
import csv
from pathlib import Path
from playwright.async_api import async_playwright

# ── Stealth compatible toutes versions ──
try:
    from playwright_stealth import Stealth
    STEALTH_MODE = "new"
except ImportError:
    try:
        from playwright_stealth import stealth_async
        STEALTH_MODE = "old"
    except ImportError:
        STEALTH_MODE = "none"
        print("⚠️  playwright-stealth non disponible, continuer sans stealth.")


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
EMAIL        = "riadhallouche4@gmail.com"
PASSWORD     = "Riadhhajer123"
SESSION_FILE = Path("session.json")
OUTPUT_CSV   = Path("resultats.csv")


# ─────────────────────────────────────────────
#  UTILITAIRES
# ─────────────────────────────────────────────
async def human_delay(min_ms=800, max_ms=2500):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)

async def slow_scroll(page, steps=5):
    for _ in range(steps):
        await page.mouse.wheel(0, random.randint(300, 600))
        await human_delay(400, 900)

async def apply_stealth(page):
    if STEALTH_MODE == "new":
        await Stealth().apply_stealth_async(page)
    elif STEALTH_MODE == "old":
        await stealth_async(page)


# ─────────────────────────────────────────────
#  RECHERCHE DU SLUG ENTREPRISE
# ─────────────────────────────────────────────
async def search_company_slug(page, company_name: str) -> str | None:
    """
    Cherche l'entreprise sur LinkedIn, clique sur le premier résultat
    et retourne son slug depuis l'URL.
    """
    print(f"\n🔍 Recherche de '{company_name}' sur LinkedIn...")
    search_url = f"https://www.linkedin.com/search/results/companies/?keywords={company_name.replace(' ', '%20')}"
    await page.goto(search_url, wait_until="domcontentloaded")
    await human_delay(2000, 3500)

    # ── Essaie plusieurs sélecteurs pour trouver le premier résultat ──
    selectors = [
        ".entity-result__title-text a",
        ".app-aware-link[href*='/company/']",
        "a[href*='/company/']",
    ]

    href = None
    for sel in selectors:
        try:
            el = page.locator(sel).first
            href = await el.get_attribute("href", timeout=3000)
            if href and "/company/" in href:
                break
        except Exception:
            continue

    if not href or "/company/" not in href:
        print(f"   ⚠ Aucun résultat trouvé pour '{company_name}'")
        return None

    # Extraire le slug depuis le href
    slug = href.split("/company/")[1].split("/")[0].split("?")[0]
    print(f"   ✔ Slug trouvé : '{slug}' — navigation vers la page...")

    # ── Naviguer directement vers la page entreprise ──
    await page.goto(f"https://www.linkedin.com/company/{slug}/about/", wait_until="domcontentloaded")
    await human_delay(1500, 2500)

    # Vérifier qu'on est bien sur une page entreprise
    if "/company/" not in page.url:
        print(f"   ⚠ Redirection inattendue : {page.url}")
        return None

    print(f"   ✔ Page entreprise chargée !")
    return slug


# ─────────────────────────────────────────────
#  LOGIN / SESSION
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
#  SCRAPING PAGE ENTREPRISE
# ─────────────────────────────────────────────
async def scrape_company_about(page, slug: str) -> dict:
    url = f"https://www.linkedin.com/company/{slug}/about/"
    print(f"\n🏢 Scraping infos : {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(1500, 3000)
    await slow_scroll(page, steps=4)

    data = {"slug": slug, "url": url}

    for field, selectors in {
        "nom"        : ["h1"],
        "taille"     : ["dt:has-text('Taille') + dd", "dt:has-text('Company size') + dd"],
        "secteur"    : ["dt:has-text('Secteur') + dd", "dt:has-text('Industry') + dd"],
        "siege"      : ["dt:has-text('Siège') + dd", "dt:has-text('Headquarters') + dd"],
        "specialites": ["dt:has-text('Spécialités') + dd", "dt:has-text('Specialties') + dd"],
        "services"   : ["dt:has-text('Services') + dd", "dt:has-text('Services proposés') + dd", ".org-about-company-module__service-offering", "[data-test-id='about-us__services']"],
    }.items():
        for sel in selectors:
            try:
                val = await page.locator(sel).first.inner_text(timeout=3000)
                if val:
                    data[field] = val.strip()
                    break
            except Exception:
                continue
        if field not in data:
            data[field] = None

    try:
        href = await page.locator("dt:has-text('Site') + dd a, dt:has-text('Website') + dd a").first.get_attribute("href", timeout=3000)
        data["site_web"] = href
    except Exception:
        data["site_web"] = None

    print(f"   ✔ Nom        : {data.get('nom')}")
    print(f"   ✔ Taille     : {data.get('taille')}")
    print(f"   ✔ Secteur    : {data.get('secteur')}")
    print(f"   ✔ Spécialités: {str(data.get('specialites',''))[:80]}")
    print(f"   ✔ Services   : {str(data.get('services',''))[:80]}")
    return data



# ─────────────────────────────────────────────
#  SCRAPING SERVICES
# ─────────────────────────────────────────────
async def scrape_company_services(page, slug: str) -> str:
    url = f"https://www.linkedin.com/company/{slug}/services/"
    print(f"\n🛠️  Scraping services : {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(4000, 6000)
    await slow_scroll(page, steps=5)
    await human_delay(2000, 3000)

    services = []

    # Attendre que le contenu soit chargé
    try:
        await page.wait_for_selector("main", timeout=5000)
    except Exception:
        pass

    # Cherche "Services provided" puis extrait les badges en dessous
    try:
        texts = await page.evaluate("""
            () => {
                const results = [];
                const skipWords = ['Services provided', 'Services fournis', 'Overview',
                                   'Request services', 'Availability', 'Pricing',
                                   'Contact for pricing', 'Remote', 'On-site'];

                // Trouve le titre "Services provided"
                const allEls = document.querySelectorAll('*');
                let servicesHeader = null;

                for (const el of allEls) {
                    const t = (el.innerText || '').trim();
                    if ((t === 'Services provided' || t === 'Services fournis') && el.children.length === 0) {
                        servicesHeader = el;
                        break;
                    }
                }

                if (servicesHeader) {
                    // Cherche le nextSibling ou le parent suivant qui contient les badges
                    let container = servicesHeader.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!container) break;
                        // Cherche tous les éléments frères après le header
                        const siblings = container.parentElement
                            ? Array.from(container.parentElement.children)
                            : [];
                        const idx = siblings.indexOf(container);
                        // Prend les éléments APRÈS le container du titre
                        const after = siblings.slice(idx + 1);
                        for (const sib of after) {
                            const badges = sib.querySelectorAll('span, li, a');
                            badges.forEach(b => {
                                const t = (b.innerText || '').trim();
                                if (t.length > 2 && t.length < 60 &&
                                    !skipWords.some(w => t.includes(w)) &&
                                    b.children.length === 0) {
                                    results.push(t);
                                }
                            });
                        }
                        if (results.length > 0) break;
                        container = container.parentElement;
                    }
                }
                return [...new Set(results)];
            }
        """)
        if texts:
            services = texts
    except Exception as e:
        print(f"   ⚠ JS eval erreur : {e}")

    if services:
        result = ", ".join(services)
        print(f"   ✔ Services trouvés : {result[:150]}")
        return result
    else:
        print(f"   ⚠ Aucun service trouvé sur {url}")
        return None

# ─────────────────────────────────────────────
#  SCRAPING MEMBRES
# ─────────────────────────────────────────────
async def scrape_company_members(page, slug: str, max_members=20) -> list:
    url = f"https://www.linkedin.com/company/{slug}/people/"
    print(f"\n👥 Scraping membres : {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(2000, 4000)

    for _ in range(4):
        await slow_scroll(page, steps=3)
        await human_delay(1000, 2000)

    cards = await page.locator("li.org-people-profile-card__profile-card-spacing").all()
    if not cards:
        cards = await page.locator("[data-view-name='profile-card']").all()

    print(f"   → {len(cards)} membres trouvés")
    members = []

    for card in cards[:max_members]:
        try:
            member = {}
            for key, sel in {
                "nom"  : ".org-people-profile-card__profile-title, .artdeco-entity-lockup__title",
                "poste": ".lt-line-clamp, .artdeco-entity-lockup__subtitle",
            }.items():
                try:
                    member[key] = await card.locator(sel).first.inner_text(timeout=2000)
                except Exception:
                    member[key] = None

            try:
                href = await card.locator("a").first.get_attribute("href")
                member["profil_url"] = ("https://www.linkedin.com" + href if href and href.startswith("/") else href)
            except Exception:
                member["profil_url"] = None

            members.append(member)
            print(f"   ✔ {member.get('nom')} — {member.get('poste')}")
        except Exception:
            continue

    return members


# ─────────────────────────────────────────────
#  EXPORT CSV
# ─────────────────────────────────────────────
def save_to_csv(companies_data: list):
    all_rows = []
    for company in companies_data:
        info, members = company["info"], company["membres"]
        base = {k: info.get(k) for k in ["slug","nom","taille","secteur","specialites","services","site_web"]}
        if members:
            for m in members:
                all_rows.append({**base, "membre_nom": m.get("nom"), "membre_poste": m.get("poste"), "membre_url": m.get("profil_url")})
        else:
            all_rows.append({**base, "membre_nom": None, "membre_poste": None, "membre_url": None})

    if all_rows:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n📄 Résultats sauvegardés → {OUTPUT_CSV} ({len(all_rows)} lignes)")


# ─────────────────────────────────────────────
#  BARRE DE RECHERCHE INTERACTIVE
# ─────────────────────────────────────────────
def ask_companies() -> list:
    """Demande à l'utilisateur les entreprises à scraper."""
    print("\n" + "="*50)
    print("   🔎 LinkedIn Company Scraper")
    print("="*50)
    print("Tape le nom d'une entreprise et appuie sur Entrée.")
    print("Tape 'fin' quand tu as terminé ta liste.\n")

    companies = []
    while True:
        name = input("🏢 Entreprise : ").strip()
        if name.lower() in ("fin", "exit", "stop", ""):
            if not companies:
                print("⚠️  Aucune entreprise saisie. Relance le script.")
                exit()
            break
        companies.append(name)
        print(f"   ✅ Ajouté : {name}")

    print(f"\n📋 {len(companies)} entreprise(s) à scraper : {', '.join(companies)}\n")
    return companies


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
async def main():
    # 1. Demande les entreprises AVANT de lancer le navigateur
    company_names = ask_companies()
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
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
        page = await context.new_page()
        await apply_stealth(page)

        # Login
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

        for name in company_names:
            try:
                # Recherche automatique du slug
                slug = await search_company_slug(page, name)
                if not slug:
                    print(f"❌ Entreprise '{name}' introuvable, ignorée.")
                    continue

                info     = await scrape_company_about(page, slug)
                services = await scrape_company_services(page, slug)
                info["services"] = services
                membres  = await scrape_company_members(page, slug, max_members=20)
                results.append({"info": info, "membres": membres})

                wait = random.uniform(5, 10)
                print(f"\n⏳ Pause {wait:.1f}s...")
                await asyncio.sleep(wait)

            except Exception as e:
                print(f"❌ Erreur pour '{name}' : {e}")
                continue

        await browser.close()

    save_to_csv(results)
    print("\n✅ Scraping terminé !")


if __name__ == "__main__":
    asyncio.run(main())