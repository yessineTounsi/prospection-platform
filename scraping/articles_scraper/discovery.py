"""
discovery.py — Version simplifiée sans système de priorité.
Logique : trouve les sections news/blog → extrait les liens → retourne MAX_DISCOVERY_URLS URLs.
Le tri par date et la limite de 15 sont gérés dans main.py.
"""

import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    SITEMAP_PATHS, SITEMAP_CONTENT_KEYWORDS,
    NAV_KEYWORDS, HARDCODED_PATHS, BAD_PATH_PATTERNS,
    BAD_EXTENSIONS, MAX_PAGINATION_PAGES,
    MAX_DISCOVERY_URLS, MIN_ARTICLE_PATH_LENGTH,
    session
)
from fetcher import fetch_page, fetch_page_dynamic
from utils import clean_text, get_browser_headers


# ─────────────────────────────────────────────
#  UTILITAIRES
# ─────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def _has_bad_extension(path: str) -> bool:
    ext = "." + path.rsplit(".", 1)[-1] if "." in path.split("/")[-1] else ""
    return ext in BAD_EXTENSIONS


def _is_same_domain(url: str, domain: str) -> bool:
    netloc = urlparse(url).netloc
    return domain in netloc or netloc.endswith("." + domain)


def _is_news_section_url(url: str) -> bool:
    """Retourne True si cette URL est une section news/blog."""
    parsed    = urlparse(url)
    subdomain = parsed.netloc.split(".")[0].lower()

    # Sous-domaine blog.* / news.* / press.*
    if subdomain in ["blog", "news", "press", "presse", "actualites",
                     "media", "newsroom", "insights"]:
        return True

    path     = parsed.path.lower().rstrip("/")
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False

    _KEYWORDS = [
        "blog", "news", "newsroom", "actualite", "actualites",
        "actualité", "actualités", "presse", "press", "articles",
        "insights", "publications", "stories", "announcements",
        "evenements", "événements", "events", "journal", "magazine",
        "revue", "nouvelles", "communiques", "communiqués",
        "noticias", "notícias", "akhbar",
    ]

    last = segments[-1]
    for kw in _KEYWORDS:
        if kw == last or last.startswith(kw) or last.endswith(kw):
            return True
    if len(segments) >= 2:
        for kw in _KEYWORDS:
            if kw == segments[-2]:
                return True
    return False


def _get_main_content_soup(html: str) -> BeautifulSoup:
    """Supprime nav/header/footer pour ne garder que le contenu principal."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["nav", "header", "footer"]):
        tag.decompose()
    return soup


# ─────────────────────────────────────────────
#  STRATÉGIE 1 : SITEMAP
# ─────────────────────────────────────────────

def _parse_sitemap_urls(xml_text: str, base_domain: str) -> list:
    urls = []
    try:
        root = ET.fromstring(xml_text)
        ns   = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for sitemap_tag in root.findall(".//sm:sitemap/sm:loc", ns):
            sub_url = sitemap_tag.text.strip()
            if any(kw in sub_url.lower() for kw in SITEMAP_CONTENT_KEYWORDS):
                try:
                    sub_xml = fetch_page(sub_url)
                    urls.extend(_parse_sitemap_urls(sub_xml, base_domain))
                except Exception:
                    continue
        for url_tag in root.findall(".//sm:url/sm:loc", ns):
            u = url_tag.text.strip()
            if base_domain in u:
                urls.append(u)
    except ET.ParseError:
        pass
    return urls


def discover_urls_via_sitemap(base_url: str, domain: str) -> list:
    parsed = urlparse(base_url)
    base   = f"{parsed.scheme}://{parsed.netloc}"
    found  = []
    for path in SITEMAP_PATHS:
        try:
            xml  = fetch_page(urljoin(base, path))
            urls = _parse_sitemap_urls(xml, domain)
            for u in urls:
                p = urlparse(u).path.lower()
                if any(kw in p for kw in SITEMAP_CONTENT_KEYWORDS):
                    found.append(u)
            if found:
                print(f"[SITEMAP] {len(found)} URL(s)")
                break
        except Exception:
            continue
    return list(set(found))


# ─────────────────────────────────────────────
#  STRATÉGIE 2 : NAVIGATION
# ─────────────────────────────────────────────

def discover_content_sections_from_nav(base_url: str, domain: str) -> list:
    """
    Analyse toute la page pour trouver les sections news/blog,
    y compris les sous-sections dans les menus déroulants.
    Détecte aussi les sous-domaines blog.*, news.*...
    """
    try:
        html = fetch_page(base_url, use_dynamic_fallback=True)   # Playwright pour sites JS
    except Exception:
        return []

    soup         = BeautifulSoup(html, "html.parser")
    parsed_base  = urlparse(base_url)
    base         = f"{parsed_base.scheme}://{parsed_base.netloc}"
    section_urls = set()

    for a in soup.find_all("a", href=True):
        full_url = urljoin(base, a["href"].strip())
        if not _is_same_domain(full_url, domain):
            continue
        text  = clean_text(a.get_text()).lower()
        path  = urlparse(full_url).path.lower()
        query = urlparse(full_url).query.lower()
        if any(kw in text or kw in path or kw in query for kw in NAV_KEYWORDS):
            section_urls.add(_normalize_url(full_url))

    print(f"[NAV] {len(section_urls)} section(s) : {list(section_urls)}")
    return list(section_urls)


# ─────────────────────────────────────────────
#  STRATÉGIE 3 : PATHS HARDCODÉS (en parallèle)
# ─────────────────────────────────────────────

def discover_urls_via_hardcoded_paths(base_url: str, domain: str) -> list:
    """Teste tous les paths hardcodés en parallèle (10 threads)."""
    parsed = urlparse(base_url)
    base   = f"{parsed.scheme}://{parsed.netloc}"
    found  = []

    def _test(path):
        full_url = _normalize_url(urljoin(base, path))
        try:
            r = session.get(full_url, headers=get_browser_headers(),
                           timeout=5, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                return full_url
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_test, p): p for p in HARDCODED_PATHS}
        for future in as_completed(futures):
            result = future.result()
            if result:
                found.append(result)

    print(f"[HARDCODED] {len(found)} section(s)")
    return found


# ─────────────────────────────────────────────
#  EXTRACTION DE LIENS DEPUIS UNE SECTION NEWS
# ─────────────────────────────────────────────

def extract_links_from_section(page_url: str, domain: str) -> list:
    """
    Extrait les liens depuis une section news/blog.
    Supprime nav/header/footer → prend tout le reste.
    Filtre minimal : même domaine, pas image/PDF, pas la section elle-même.
    """
    def _extract(html: str) -> list:
        soup  = _get_main_content_soup(html)
        links = []
        seen  = set()
        for a in soup.find_all("a", href=True):
            full_url = urljoin(page_url, a["href"].strip())
            if not _is_same_domain(full_url, domain):
                continue
            clean_url = _normalize_url(full_url)
            if clean_url in seen:
                continue
            path = urlparse(full_url).path.lower().rstrip("/")
            if not path or path == "/":
                continue
            if _has_bad_extension(path):
                continue
            if clean_url == _normalize_url(page_url):
                continue
            if "/wp-content/" in path or "/uploads/" in path:
                continue
            seen.add(clean_url)
            links.append(clean_url)
        return links

    links = []
    try:
        links = _extract(fetch_page(page_url))
    except Exception:
        pass

    # Fallback Playwright si peu de liens (site JS dynamique)
    if len(links) < 3:
        try:
            links = _extract(fetch_page_dynamic(page_url))
        except Exception:
            pass

    return links


# ─────────────────────────────────────────────
#  PAGINATION
# ─────────────────────────────────────────────

def paginate_listing_page(listing_url: str, domain: str,
                          max_pages: int = MAX_PAGINATION_PAGES) -> list:
    pages = [listing_url]
    if max_pages <= 1:
        return pages

    try:
        html     = fetch_page(listing_url)
        soup     = BeautifulSoup(html, "html.parser")
        next_url = None

        for a in soup.find_all("a", href=True):
            text = clean_text(a.get_text()).lower()
            href = urljoin(listing_url, a["href"].strip())
            if text in ["next", "›", "»", "suivant", "suivante", "2"]:
                next_url = href
                break
            if re.search(r'[/=]2/?$', urlparse(href).path + "?" + urlparse(href).query):
                next_url = href
                break

        if not next_url:
            return pages

        PATTERNS = [
            lambda base, n: f"{base.rstrip('/')}/page/{n}/",
            lambda base, n: f"{base.rstrip('/')}/page/{n}",
            lambda base, n: f"{base}?page={n}",
            lambda base, n: f"{base}?paged={n}",
            lambda base, n: f"{base}?p={n}",
        ]

        candidate = None
        for pattern in PATTERNS:
            if _normalize_url(pattern(listing_url, 2)) == _normalize_url(next_url):
                candidate = pattern
                break

        if candidate:
            for n in range(2, max_pages + 1):
                url = candidate(listing_url, n)
                try:
                    html = fetch_page(url)
                    if not html or len(html) < 500:
                        break
                    pages.append(url)
                except Exception:
                    break
        else:
            current = next_url
            for _ in range(max_pages - 1):
                if current in pages:
                    break
                pages.append(current)
                try:
                    html = fetch_page(current)
                    soup = BeautifulSoup(html, "html.parser")
                    nxt  = None
                    for a in soup.find_all("a", href=True):
                        if clean_text(a.get_text()).lower() in ["next", "›", "»", "suivant"]:
                            nxt = urljoin(current, a["href"])
                            break
                    if not nxt or nxt in pages:
                        break
                    current = nxt
                except Exception:
                    break

    except Exception:
        pass

    return pages


# ─────────────────────────────────────────────
#  ORCHESTRATEUR PRINCIPAL — SIMPLIFIÉ
# ─────────────────────────────────────────────

def discover_all_article_urls(company_url: str, company_info: dict) -> list:
    """
    Version simplifiée sans système de priorité.
    1. Trouve toutes les sections news/blog du site
    2. Extrait les liens de chaque section
    3. Retourne jusqu'à MAX_DISCOVERY_URLS URLs uniques
    """
    domain      = company_info["domain"]
    all_urls    = set()
    all_sections = set()

    print("\n[DÉCOUVERTE] Lancement...")

    # ── 1. Sitemap → URLs directes d'articles
    sitemap_urls = discover_urls_via_sitemap(company_url, domain)
    all_urls.update(sitemap_urls)

    # ── 2. Sections via navigation
    nav_sections = discover_content_sections_from_nav(company_url, domain)
    all_sections.update(nav_sections)

    # ── 3. Sections via paths hardcodés
    hardcoded = discover_urls_via_hardcoded_paths(company_url, domain)
    all_sections.update(hardcoded)

    # ── Déduplication des sections par URL finale (après redirection)
    seen_finals = set()
    unique_sections = []
    for s in all_sections:
        try:
            r = session.get(s, headers=get_browser_headers(),
                           timeout=5, allow_redirects=True)
            final = _normalize_url(r.url)
            if final in seen_finals:
                continue
            seen_finals.add(final)
        except Exception:
            pass
        if _normalize_url(s) not in seen_finals:
            seen_finals.add(_normalize_url(s))
        unique_sections.append(s)

    # Garde seulement les sections news
    news_sections = [s for s in unique_sections if _is_news_section_url(s)]
    other_sections = [s for s in unique_sections if not _is_news_section_url(s)]

    print(f"[SECTIONS NEWS] {len(news_sections)} : {news_sections}")
    print(f"[SECTIONS AUTRES] {len(other_sections)}")

    # ── 4. Extraction des liens depuis les sections news
    for section_url in news_sections:
        try:
            for page_url in paginate_listing_page(section_url, domain):
                links = extract_links_from_section(page_url, domain)
                all_urls.update(links)
                print(f"  [NEWS] {section_url} → {len(links)} lien(s)")
                if len(all_urls) >= MAX_DISCOVERY_URLS:
                    break
        except Exception as e:
            print(f"  [WARN] {section_url} : {e}")
        if len(all_urls) >= MAX_DISCOVERY_URLS:
            break

    # ── 5. Si pas assez → sections génériques
    if len(all_urls) < MAX_DISCOVERY_URLS:
        for section_url in other_sections:
            try:
                links = extract_links_from_section(section_url, domain)
                all_urls.update(links)
            except Exception:
                pass

    # ── 6. Si toujours rien → homepage en dernier recours
    if not all_urls and not news_sections:
        print("[INFO] Aucune section trouvée → homepage")
        links = extract_links_from_section(company_url, domain)
        all_urls.update(links)

    # ── Filtre final : retire les sections elles-mêmes
    section_norms = {_normalize_url(s) for s in all_sections}
    filtered = [
        u for u in all_urls
        if _normalize_url(u) not in section_norms
        and _is_same_domain(u, domain)
        and not _has_bad_extension(urlparse(u).path.lower())
        and urlparse(u).path.lower() not in ["/", ""]
    ]

    # Déduplique
    seen = set()
    result = []
    for u in filtered:
        n = _normalize_url(u)
        if n not in seen:
            seen.add(n)
            result.append(u)

    result = result[:MAX_DISCOVERY_URLS]
    print(f"\n[DÉCOUVERTE] {len(result)} URL(s) trouvées")
    return result