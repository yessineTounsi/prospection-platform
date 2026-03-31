import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

from config import (
    SITEMAP_PATHS, SITEMAP_CONTENT_KEYWORDS,
    NAV_KEYWORDS, HARDCODED_PATHS, BAD_PATH_PATTERNS,
    MAX_PAGINATION_PAGES, MAX_DISCOVERY_URLS, MIN_ARTICLE_PATH_LENGTH
)
from fetcher import fetch_page, fetch_page_dynamic
from utils import clean_text


# ─────────────────────────────────────────────
#  FILTRAGE D'URLS
# ─────────────────────────────────────────────

def is_excluded_url(url: str) -> bool:
    """
    Retourne True si l'URL ne peut pas être un article.
    Vérifie : patterns explicites, chemin trop court, segment numérique seul.
    """
    parsed = urlparse(url)
    path   = parsed.path.lower().rstrip("/")

    if not path or path == "/":
        return True

    # Patterns explicites (config.py)
    if any(p in path for p in BAD_PATH_PATTERNS):
        return True

    # Chemin trop court = page de catégorie/service
    if len(path) < MIN_ARTICLE_PATH_LENGTH:
        return True

    # Dernier segment purement numérique = pagination résiduelle
    if path.split("/")[-1].isdigit():
        return True

    return False


def _path_looks_like_article(path: str) -> bool:
    """
    Heuristique positive : est-ce que ce chemin ressemble à un slug d'article ?
    - Contient un mot-clé de contenu (/blog/, /news/, /post/…)
    - Contient une date /2024/ ou /2023/
    - Dernier segment long avec tirets (titre d'article typique)
    """
    p = path.lower()

    if any(kw in p for kw in SITEMAP_CONTENT_KEYWORDS):
        return True

    if re.search(r'/20\d{2}/', p):
        return True

    last = p.rstrip("/").split("/")[-1]
    if len(last) >= 20 and last.count("-") >= 2:
        return True

    return False


# ─────────────────────────────────────────────
#  STRATÉGIE 1 : SITEMAP XML
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
                if any(kw in p for kw in SITEMAP_CONTENT_KEYWORDS) and not is_excluded_url(u):
                    found.append(u)
                if len(found) >= MAX_DISCOVERY_URLS:
                    break
            if found:
                print(f"[SITEMAP] {len(found)} URL(s) trouvée(s) via {path}")
                break
        except Exception:
            continue

    return list(set(found))


# ─────────────────────────────────────────────
#  STRATÉGIE 2 : NAVIGATION DU SITE
# ─────────────────────────────────────────────

def discover_content_sections_from_nav(base_url: str, domain: str) -> list:
    try:
        html = fetch_page(base_url, use_dynamic_fallback=True)
    except Exception:
        return []

    soup         = BeautifulSoup(html, "html.parser")
    parsed_base  = urlparse(base_url)
    base         = f"{parsed_base.scheme}://{parsed_base.netloc}"
    section_urls = set()

    for container in soup.find_all(["nav", "header", "footer"]):
        for a in container.find_all("a", href=True):
            full_url = urljoin(base, a["href"].strip())
            if domain not in urlparse(full_url).netloc:
                continue
            text = clean_text(a.get_text()).lower()
            path = urlparse(full_url).path.lower()
            if any(kw in text or kw in path for kw in NAV_KEYWORDS):
                section_urls.add(full_url)

    print(f"[NAV] {len(section_urls)} section(s) de contenu détectée(s)")
    return list(section_urls)


# ─────────────────────────────────────────────
#  STRATÉGIE 3 : PATHS HARDCODÉS
# ─────────────────────────────────────────────

def discover_urls_via_hardcoded_paths(base_url: str, domain: str) -> list:
    parsed = urlparse(base_url)
    base   = f"{parsed.scheme}://{parsed.netloc}"
    found  = []

    for path in HARDCODED_PATHS:
        full_url = urljoin(base, path)
        try:
            html = fetch_page(full_url)
            if html and len(html) > 500:
                found.append(full_url)
        except Exception:
            continue

    print(f"[HARDCODED] {len(found)} page(s) trouvée(s)")
    return found


# ─────────────────────────────────────────────
#  PAGINATION
# ─────────────────────────────────────────────

PAGINATION_PATTERNS = [
    lambda base, n: f"{base.rstrip('/')}/page/{n}/",
    lambda base, n: f"{base.rstrip('/')}/page/{n}",
    lambda base, n: f"{base}?page={n}",
    lambda base, n: f"{base}?p={n}",
    lambda base, n: f"{base}?offset={(n - 1) * 10}",
]


def paginate_listing_page(listing_url: str, domain: str,
                          max_pages: int = MAX_PAGINATION_PAGES) -> list:
    """Page 1 uniquement si MAX_PAGINATION_PAGES = 1."""
    return [listing_url] if max_pages <= 1 else [listing_url]


# ─────────────────────────────────────────────
#  EXTRACTION DES LIENS D'ARTICLES
# ─────────────────────────────────────────────

def _looks_like_article_link(a_tag, listing_url: str) -> bool:
    """
    Vérifie si un <a> pointe vers un vrai article.
    Priorité au chemin lui-même (heuristique _path_looks_like_article).
    """
    href = a_tag.get("href", "")
    if not href:
        return False

    full_url = urljoin(listing_url, href)
    path     = urlparse(full_url).path.lower()

    # ── Filtre 1 : le chemin doit ressembler à un article
    if not _path_looks_like_article(path):
        return False

    # ── Filtre 2 : contexte DOM ou texte long
    text = clean_text(a_tag.get_text(" ", strip=True))

    parent = a_tag
    for _ in range(5):
        if parent is None:
            break
        classes  = " ".join(parent.get("class", [])).lower()
        tag_name = (parent.name or "").lower()
        if tag_name == "article":
            return True
        if any(kw in classes for kw in [
            "post", "article", "news", "card", "item", "teaser",
            "entry", "content", "story", "blog", "insight"
        ]):
            return True
        parent = parent.parent

    if len(text) >= 30:
        return True
    if len(clean_text(a_tag.get("title", ""))) >= 30:
        return True

    return False


def extract_article_links_from_page(page_url: str, domain: str) -> list:
    def _extract(html: str) -> set:
        soup  = BeautifulSoup(html, "html.parser")
        links = set()
        for a in soup.find_all("a", href=True):
            full_url  = urljoin(page_url, a["href"].strip())
            parsed    = urlparse(full_url)
            if domain not in parsed.netloc:
                continue
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            if is_excluded_url(clean_url):
                continue
            if not _looks_like_article_link(a, page_url):
                continue
            links.add(clean_url)
            if len(links) >= MAX_DISCOVERY_URLS:
                break
        return links

    links = set()
    try:
        links = _extract(fetch_page(page_url))
    except Exception:
        pass

    if len(links) < 3:
        try:
            links = _extract(fetch_page_dynamic(page_url))
        except Exception:
            pass

    return list(links)


# ─────────────────────────────────────────────
#  ORCHESTRATEUR PRINCIPAL
# ─────────────────────────────────────────────

def discover_all_article_urls(company_url: str, company_info: dict) -> list:
    """
    Orchestre les 4 stratégies.

    ⚠️  La homepage n'est PAS ajoutée comme page de listing par défaut —
    elle contient des liens de navigation/marketplace qui polluent les résultats.
    Elle n'est utilisée qu'en dernier recours si aucune section n'est trouvée.
    """
    domain           = company_info["domain"]
    all_article_urls = set()
    listing_pages    = set()

    print("\n[DÉCOUVERTE] Lancement des 4 stratégies...")

    # ── 1. Sitemap (source la plus fiable)
    sitemap_urls = discover_urls_via_sitemap(company_url, domain)
    all_article_urls.update(sitemap_urls)
    if len(all_article_urls) >= MAX_DISCOVERY_URLS:
        print(f"[DÉCOUVERTE] Limite atteinte via sitemap")
        return list(all_article_urls)[:MAX_DISCOVERY_URLS]

    # ── 2. Navigation → sections blog/news
    nav_sections = discover_content_sections_from_nav(company_url, domain)
    listing_pages.update(nav_sections)

    # ── 3. Paths hardcodés
    listing_pages.update(discover_urls_via_hardcoded_paths(company_url, domain))

    # ── Homepage uniquement si AUCUNE section trouvée
    if not listing_pages:
        print("[WARN] Aucune section de contenu trouvée — utilisation de la homepage")
        listing_pages.add(company_url)

    # ── 4. Extraction des liens d'articles depuis chaque section
    print(f"\n[PAGINATION] Analyse de {len(listing_pages)} section(s)...")
    for section_url in listing_pages:
        try:
            for page_url in paginate_listing_page(section_url, domain):
                links = extract_article_links_from_page(page_url, domain)
                all_article_urls.update(links)
                if len(all_article_urls) >= MAX_DISCOVERY_URLS:
                    break
        except Exception as e:
            print(f"  [WARN] {section_url} : {e}")
        if len(all_article_urls) >= MAX_DISCOVERY_URLS:
            break

    # ── Filtre final triple
    filtered = {
        u for u in all_article_urls
        if not is_excluded_url(u)
        and domain in urlparse(u).netloc
        and _path_looks_like_article(urlparse(u).path.lower())
    }

    print(f"\n[DÉCOUVERTE] {len(filtered)} URL(s) d'articles valides trouvées")
    return list(filtered)