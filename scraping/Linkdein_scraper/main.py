"""
LinkedIn Company Scraper
========================
Lancement : python main.py

Modules :
    config.py    → credentials et chemins
    utils.py     → helpers (délais, scroll, nettoyage)
    browser.py   → navigateur, login, session
    scraper.py   → scraping (recherche, infos, services, membres)
    exporter.py  → export JSON et CSV
"""

import asyncio
import random
from playwright.async_api import async_playwright

from config import MAX_MEMBERS
from browser import create_browser, apply_stealth, ensure_logged_in
from scraper import search_company_slug, scrape_company_about, scrape_company_services, scrape_company_members
from exporter import save_to_json, save_to_csv


def ask_companies() -> list:
    print("\n" + "="*50)
    print("   🔎 LinkedIn Company Scraper")
    print("="*50)
    print("Tape le nom d'une entreprise et appuie sur Entrée.")
    print("Tape 'fin' pour lancer le scraping.\n")

    companies = []
    while True:
        name = input("🏢 Entreprise : ").strip()
        if name.lower() in ("fin", "exit", "stop", ""):
            if not companies:
                print("⚠️  Aucune entreprise saisie.")
                exit()
            break
        companies.append(name)
        print(f"   ✅ Ajouté : {name}")

    print(f"\n📋 {len(companies)} entreprise(s) : {', '.join(companies)}\n")
    return companies


async def main():
    company_names = ask_companies()
    results = []

    async with async_playwright() as p:
        browser, context = await create_browser(p)
        page = await context.new_page()
        await apply_stealth(page)
        await ensure_logged_in(page, context)

        for name in company_names:
            try:
                slug = await search_company_slug(page, name)
                if not slug:
                    print(f"❌ '{name}' introuvable, ignorée.")
                    continue

                info     = await scrape_company_about(page, slug)
                services = await scrape_company_services(page, slug)
                info["services"] = services
                membres  = await scrape_company_members(page, slug, max_members=MAX_MEMBERS)

                results.append({"info": info, "membres": membres})

                wait = random.uniform(5, 10)
                print(f"\n⏳ Pause {wait:.1f}s...")
                await asyncio.sleep(wait)

            except Exception as e:
                print(f"❌ Erreur '{name}' : {e}")
                continue

        await browser.close()

    save_to_json(results)
    save_to_csv(results)
    print("\n✅ Scraping terminé !")


if __name__ == "__main__":
    asyncio.run(main())