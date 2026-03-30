from utils import human_delay, slow_scroll, clean_text, clean_url


async def search_company_slug(page, company_name: str) -> str | None:
    print(f"\n🔍 Recherche de '{company_name}'...")
    url = f"https://www.linkedin.com/search/results/companies/?keywords={company_name.replace(' ', '%20')}"
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(2000, 3500)

    href = None
    for sel in [".entity-result__title-text a", ".app-aware-link[href*='/company/']", "a[href*='/company/']"]:
        try:
            href = await page.locator(sel).first.get_attribute("href", timeout=3000)
            if href and "/company/" in href:
                break
        except Exception:
            continue

    if not href or "/company/" not in href:
        print(f"   ⚠ Introuvable : '{company_name}'")
        return None

    slug = href.split("/company/")[1].split("/")[0].split("?")[0]
    print(f"   ✔ Slug : '{slug}'")

    await page.goto(f"https://www.linkedin.com/company/{slug}/about/", wait_until="domcontentloaded")
    await human_delay(1500, 2500)

    if "/company/" not in page.url:
        print(f"   ⚠ Redirection inattendue : {page.url}")
        return None

    return slug


async def scrape_company_about(page, slug: str) -> dict:
    url = f"https://www.linkedin.com/company/{slug}/about/"
    print(f"\n🏢 Infos entreprise : {url}")
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
        data["site_web"] = await page.locator(
            "dt:has-text('Site') + dd a, dt:has-text('Website') + dd a"
        ).first.get_attribute("href", timeout=3000)
    except Exception:
        data["site_web"] = None

    print(f"   ✔ {data.get('nom')} | {data.get('taille')} | {data.get('secteur')}")
    return data


async def scrape_company_services(page, slug: str) -> str | None:
    url = f"https://www.linkedin.com/company/{slug}/services/"
    print(f"\n🛠️  Services : {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await human_delay(4000, 6000)
    await slow_scroll(page, steps=5)
    await human_delay(2000, 3000)

    try:
        await page.wait_for_selector("main", timeout=5000)
    except Exception:
        pass

    try:
        texts = await page.evaluate("""
            () => {
                const skip = ['Services provided','Services fournis','Overview',
                              'Request services','Availability','Pricing',
                              'Contact for pricing','Remote','On-site'];
                let header = null;
                for (const el of document.querySelectorAll('*')) {
                    const t = (el.innerText || '').trim();
                    if ((t === 'Services provided' || t === 'Services fournis') && el.children.length === 0) {
                        header = el; break;
                    }
                }
                if (!header) return [];
                const results = [];
                let container = header.parentElement;
                for (let i = 0; i < 6; i++) {
                    if (!container) break;
                    const siblings = container.parentElement
                        ? Array.from(container.parentElement.children) : [];
                    const idx = siblings.indexOf(container);
                    for (const sib of siblings.slice(idx + 1)) {
                        sib.querySelectorAll('span, li, a').forEach(b => {
                            const t = (b.innerText || '').trim();
                            if (t.length > 2 && t.length < 60 &&
                                !skip.some(w => t.includes(w)) &&
                                b.children.length === 0) results.push(t);
                        });
                    }
                    if (results.length > 0) break;
                    container = container.parentElement;
                }
                return [...new Set(results)];
            }
        """)
        if texts:
            result = ", ".join(texts)
            print(f"   ✔ Services : {result[:120]}")
            return result
    except Exception as e:
        print(f"   ⚠ Erreur JS : {e}")

    print("   ⚠ Aucun service trouvé")
    return None


async def scrape_company_members(page, slug: str, max_members: int = 20) -> list:
    url = f"https://www.linkedin.com/company/{slug}/people/"
    print(f"\n👥 Membres : {url}")
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

            # Nom
            for sel in [
                ".org-people-profile-card__profile-title",
                ".artdeco-entity-lockup__title",
                "span.t-16",
                "a span[aria-hidden='true']",
            ]:
                try:
                    val = await card.locator(sel).first.inner_text(timeout=1500)
                    if val and val.strip():
                        member["nom"] = val.strip()
                        break
                except Exception:
                    continue

            # Poste via JS
            try:
                poste = await card.evaluate("""el => {
                    const sels = [
                        '.artdeco-entity-lockup__subtitle',
                        '.lt-line-clamp--multi-line',
                        '.org-people-profile-card__profile-position',
                        '[class*="subtitle"]', '[class*="position"]',
                        '[class*="headline"]', 'div.t-14', 'span.t-14',
                    ];
                    for (const s of sels) {
                        const e = el.querySelector(s);
                        if (e && e.innerText.trim().length > 1) return e.innerText.trim();
                    }
                    const texts = [];
                    el.querySelectorAll('span, div').forEach(s => {
                        const t = s.innerText ? s.innerText.trim() : '';
                        if (t.length > 2 && s.children.length === 0) texts.push(t);
                    });
                    return texts.length > 1 ? texts[1] : '';
                }""")
                member["poste"] = poste.strip() if poste else ""
            except Exception:
                member["poste"] = ""

            # URL profil
            try:
                href = await card.locator("a").first.get_attribute("href")
                member["profil_url"] = (
                    "https://www.linkedin.com" + href if href and href.startswith("/") else href
                )
            except Exception:
                member["profil_url"] = None

            members.append(member)
            print(f"   ✔ {member.get('nom')} — {member.get('poste') or '—'}")

        except Exception:
            continue

    return members