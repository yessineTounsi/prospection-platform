import requests
import cloudscraper
import trafilatura
from bs4 import BeautifulSoup
import re
import json
import sqlite3
import csv
import time
import random
import certifi
import urllib3
from playwright.sync_api import sync_playwright
from datetime import datetime, UTC
from urllib.parse import urlparse, urljoin, quote
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
API_KEY = "ad38b88faa7956fac8640062bd3702b4"
REQUEST_TIMEOUT = 25
MIN_DELAY = 1.0
MAX_DELAY = 2.0
FILTER_NEGATIVE_THRESHOLD = 0
session = requests.Session()
cloud_session = cloudscraper.create_scraper(browser={
    "browser": "chrome",
    "platform": "windows",
    "mobile": False
})
def fetch_page_dynamic(url, wait_seconds=3):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(wait_seconds * 1000)
        html = page.content()
        browser.close()
        return html
def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()
def random_delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
def get_browser_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }
def extract_meta(soup, attr_name, attr_value):
    tag = soup.find("meta", attrs={attr_name: attr_value})
    if tag and tag.get("content"):
        return clean_text(tag["content"])
    return ""
def detect_language(text):
    text = f" {(text or '').lower()} "
    french_words = [" le ", " la ", " les ", " de ", " des ", " et ", " pour ", " avec ", " une ", " un "]
    english_words = [" the ", " and ", " for ", " with ", " of ", " in ", " on ", " a ", " an "]
    fr_score = sum(word in text for word in french_words)
    en_score = sum(word in text for word in english_words)
    return "fr" if fr_score > en_score else "en"
def flatten_for_csv(value):
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value
def fetch_page(url):
    random_delay()
    headers = get_browser_headers()
    try:
        response = session.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            verify=certifi.where()
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.SSLError:
        print(f"[WARN] SSL error sur {url}, nouvelle tentative sans vérification SSL")
        try:
            response = session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                verify=False
            )
            response.raise_for_status()
            return response.text
        except Exception:
            response = cloud_session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                verify=False
            )
            response.raise_for_status()
            return response.text
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status in [403, 406, 429]:
            random_delay()
            response = cloud_session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                verify=False
            )
            response.raise_for_status()
            return response.text
        raise
    except Exception:
        random_delay()
        response = cloud_session.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            verify=False
        )
        response.raise_for_status()
        return response.text
def normalize_company_name(name):
    if not name:
        return ""
    name = clean_text(name)
    separators = ["|", " - ", " — ", ":", "•"]
    for sep in separators:
        if sep in name:
            parts = [clean_text(part) for part in name.split(sep)]
            parts = [p for p in parts if p]
            if parts:
                name = parts[0]
                break
    generic_names = {
        "home", "welcome", "official site", "homepage",
        "website", "site", "blog", "news"
    }
    if len(name) < 3:
        return ""

    if name.lower() in generic_names:
        return ""
    return name
def domain_to_company_name(domain):
    base = domain.split(".")[0]
    base = base.replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in base.split())
def detect_company_info(company_url):
    html = fetch_page(company_url)
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(company_url).netloc.replace("www.", "")
    title = clean_text(soup.title.get_text()) if soup.title else ""
    og_title = extract_meta(soup, "property", "og:title")
    site_name = extract_meta(soup, "property", "og:site_name")
    description = (
        extract_meta(soup, "name", "description") or
        extract_meta(soup, "property", "og:description")
    )
    h1 = soup.find("h1")
    h1_text = clean_text(h1.get_text()) if h1 else ""
    candidates = [
        normalize_company_name(site_name),
        normalize_company_name(title),
        normalize_company_name(og_title),
        normalize_company_name(h1_text),
        domain_to_company_name(domain)
    ]
    company_name = ""
    for c in candidates:
        if c:
            company_name = c
            break
    aliases = set()
    if company_name:
        aliases.add(company_name)
    aliases.add(domain.split(".")[0])
    aliases.add(domain_to_company_name(domain))
    aliases = {clean_text(a) for a in aliases if a and len(a) >= 2}
    return {
        "company_name": company_name,
        "domain": domain,
        "aliases": list(aliases),
        "description": description
    }
def search_company_articles_gnews(company_info, max_results=50):
    aliases = company_info["aliases"]
    queries = []
    for alias in aliases:
        queries.append(f'"{alias}"')
        queries.append(f'"{alias}" news')
    all_articles = []
    seen_urls = set()
    for query in queries:
        time.sleep(2)
        url = (
            "https://gnews.io/api/v4/search?"
            f"q={quote(query)}&lang=en&max={max_results}&apikey={API_KEY}"
        )
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        for item in data.get("articles", []):
            article_url = item.get("url", "")
            if not article_url or article_url in seen_urls:
                continue
            seen_urls.add(article_url)
            all_articles.append({
                "source_type": "external_news",
                "titre_rss": item.get("title", ""),
                "url": article_url,
                "date_rss": item.get("publishedAt", ""),
                "resume_rss": item.get("description", ""),
                "source_rss": item.get("source", {}).get("name", "")
            })
    return all_articles
def is_real_article(url, text):
    url = url.lower()
    bad_words = [
        "about",
        "team",
        "career",
        "job",
        "service",
        "legal",
        "privacy",
        "contact",
        "mission",
        "vision",
        "strategy"
    ]
    if any(word in url for word in bad_words):
        return False
    if not text or len(text) < 400:
        return False
    paragraphs = text.count("\n")
    if paragraphs < 5:
        return False
    return True
def discover_company_content_pages(company_url):
    parsed = urlparse(company_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [
    "/",
    "Newsroom"
    "/blog",
    "/news",
    "/insights",
    "/articles",
    "/resources",
    "/press",
    "/updates",
    "/media",
    "/publications",
    "/en/news"
    "fr/news"
    "/en/News",
    "/fr/News",
    "/en/blog",
    "/fr/blog"
]
    found_pages = []
    seen = set()
    for path in candidates:
        full_url = urljoin(base, path)
        if full_url in seen:
            continue
        seen.add(full_url)
        try:
            html = fetch_page(full_url)
            if html and len(html) > 200:
                found_pages.append(full_url)
        except Exception:
            continue
    return found_pages
def is_excluded_url(url):
    path = urlparse(url).path.lower()
    excluded_patterns = [
        "/page/",
        "/tag/",
        "/tags/",
        "/category/",
        "/categories/",
        "/author/",
        "/authors/",
        "/search",
        "/feed"
    ]
    if any(pattern in path for pattern in excluded_patterns):
        return True
    if path in ["", "/"]:
        return True
    return False
def looks_like_article_anchor(a_tag):
    text = clean_text(a_tag.get_text(" ", strip=True))
    if len(text) >= 20:
        return True
    parent = a_tag
    for _ in range(4):
        if parent is None:
            break
        classes = " ".join(parent.get("class", [])).lower()
        tag_name = parent.name.lower() if parent.name else ""
        if any(keyword in classes for keyword in [
            "post", "article", "news", "card", "item", "teaser", "entry", "content"
        ]):
            return True
        if tag_name in ["article"]:
            return True
        parent = parent.parent
    return False
def extract_internal_article_links(listing_url, domain):
    html = fetch_page_dynamic(listing_url)
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(listing_url, href)
        parsed = urlparse(full_url)
        if domain not in parsed.netloc:
            continue
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if is_excluded_url(clean_url):
            continue
        path = parsed.path.lower().rstrip("/")
        if path in ["", "/"]:
            continue
        text = clean_text(a.get_text(" ", strip=True))
        if len(text) >= 15:
            links.add(clean_url)
    return list(links)
def is_article_page(html, url):
    soup = BeautifulSoup(html, "html.parser")
    extracted_text = trafilatura.extract(html) or ""
    if len(extracted_text) > 300:
        return True
    possible_dates = [
        ("property", "article:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
        ("name", "publish-date"),
        ("name", "article:published_time")
    ]
    for attr_name, attr_value in possible_dates:
        value = extract_meta(soup, attr_name, attr_value)
        if value:
            return True
    if soup.find("article"):
        return True
    page_title = clean_text(soup.title.get_text()) if soup.title else ""
    generic_titles = {"news", "blog", "insights", "resources", "press"}
    if page_title and page_title.lower() not in generic_titles and len(page_title) > 20:
        return True
    return False
def search_company_internal_articles(company_url, company_info, max_results=None):
    domain = company_info["domain"]
    listing_pages = discover_company_content_pages(company_url)
    if company_url not in listing_pages:
        listing_pages.append(company_url)
    all_urls = []
    seen = set()
    for page in listing_pages:
        try:
            urls = extract_internal_article_links(page, domain)
            print(f"[DEBUG] {page} -> {len(urls)} lien(s) candidat(s)")
            for u in urls:
                if u in seen:
                    continue
                bad_patterns = [
                    "about",
                    "team",
                    "career",
                    "job",
                    "service",
                    "legal",
                    "privacy",
                    "contact",
                    "mission",
                    "vision",
                    "strategy"
                ]
                url_lower = u.lower()
                if any(b in url_lower for b in bad_patterns):
                    continue

                try:
                    html = fetch_page(u)

                    if not is_article_page(html, u):
                        continue

                    article = extract_article_content(u)

                    if not article:
                        continue

                    text = article.get("texte_complet", "")

                    seen.add(u)

                    all_urls.append({
                        "source_type": "company_site",
                        "titre_rss": "",
                        "url": u,
                        "date_rss": "",
                        "resume_rss": "",
                        "source_rss": domain
                    })

                    if max_results is not None and len(all_urls) >= max_results:
                        return all_urls[:max_results]

                except Exception:
                    continue

        except Exception:
            continue

    return all_urls if max_results is None else all_urls[:max_results]


def get_relevance_score(company_name, title, text):
    company = (company_name or "").lower().strip()
    title_l = (title or "").lower()
    text_l = (text or "").lower()

    score = 0

    if company and company in title_l:
        score += 3

    company_count = text_l.count(company) if company else 0
    if company_count >= 1:
        score += 2
    if company_count >= 2:
        score += 1

    negative_keywords = [
        "basketball", "football", "soccer", "golf", "tennis", "match",
        "fantasy", "shoe", "shoes", "recipe", "food", "kitchen",
        "lyrics", "coupon", "discount", "hotel", "travel"
    ]

    negative_hits = [kw for kw in negative_keywords if kw in title_l or kw in text_l]
    score -= len(negative_hits) * 3

    return score


def get_relevance_info(company_name, title, text, source=""):
    company = (company_name or "").lower().strip()
    title_l = (title or "").lower()
    text_l = (text or "").lower()

    company_in_title = company in title_l if company else False
    company_count = text_l.count(company) if company else 0

    negative_keywords = [
        "basketball", "football", "soccer", "golf", "tennis", "match",
        "fantasy", "shoe", "shoes", "recipe", "food", "kitchen",
        "lyrics", "coupon", "discount", "hotel", "travel"
    ]

    negative_hits = [kw for kw in negative_keywords if kw in title_l or kw in text_l]

    return {
        "company_in_title": company_in_title,
        "company_count_in_text": company_count,
        "negative_hits": negative_hits,
        "has_full_text": len(text_l) > 200,
        "source": source
    }


def detect_article_type(text):
    text_l = (text or "").lower()

    if any(k in text_l for k in ["stock", "shares", "valuation", "investors", "nasdaq", "market cap", "buy and hold"]):
        return "finance"
    if any(k in text_l for k in ["launch", "product", "feature", "tool", "platform", "service", "software", "app"]):
        return "product"
    if any(k in text_l for k in ["partnership", "collaboration", "partnered", "alliance"]):
        return "partnership"
    if any(k in text_l for k in ["funding", "raised", "investment round", "series a", "series b", "seed round"]):
        return "funding"

    return "general"


def classify_subject(text):
    text_lower = (text or "").lower()

    rules = {
        "levee_fonds": [
            "funding round", "raised", "raises",
            "investment round", "series a", "series b", "seed round", "fundraising"
        ],
        "nomination": [
            "appointed", "joins as", "new ceo",
            "chief executive officer", "chief technology officer", "chief financial officer"
        ],
        "nouveau_produit_service": [
            "launches", "launched", "introduces", "new product", "new service",
            "unveiled", "rolls out", "platform", "software", "app"
        ],
        "acquisition_rachat": [
            "acquisition", "acquire", "acquires", "acquired", "merger", "takeover"
        ],
        "difficulte": [
            "layoffs", "bankruptcy", "losses", "shutdown", "restructuring", "cuts workforce"
        ],
        "partenariat": [
            "partnership", "partners with", "collaboration", "alliance"
        ]
    }

    found = []
    for category, keywords in rules.items():
        for keyword in keywords:
            if keyword in text_lower:
                found.append(category)
                break

    return found if found else ["autre"]

def extract_article_content(article_url):
    try:
        html = fetch_page(article_url)
    except Exception:
        html = fetch_page_dynamic(article_url)

    soup = BeautifulSoup(html, "html.parser")

    extracted_text = trafilatura.extract(html) or ""

    title = clean_text(soup.title.get_text()) if soup.title else ""
    og_title = extract_meta(soup, "property", "og:title")
    if og_title:
        title = og_title

    author = (
        extract_meta(soup, "name", "author") or
        extract_meta(soup, "property", "article:author")
    )

    date_publication = ""
    possible_dates = [
        ("property", "article:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
        ("name", "publish-date"),
        ("name", "article:published_time")
    ]

    for attr_name, attr_value in possible_dates:
        value = extract_meta(soup, attr_name, attr_value)
        if value:
            date_publication = value
            break

    description = (
        extract_meta(soup, "name", "description") or
        extract_meta(soup, "property", "og:description")
    )

    keywords_raw = extract_meta(soup, "name", "keywords")
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()] if keywords_raw else []

    if not description:
        description = extracted_text[:300] + "..." if len(extracted_text) > 300 else extracted_text

    language = detect_language(extracted_text if extracted_text else title)
    source = urlparse(article_url).netloc.replace("www.", "")
    categories = classify_subject(extracted_text)
    article_type = detect_article_type(extracted_text)

    return {
        "titre": title,
        "source": source,
        "date_publication": date_publication,
        "url": article_url,
        "langue": language,
        "auteur": author,
        "extrait": description,
        "texte_complet": extracted_text,
        "mots_cles": keywords,
        "categories_detectees": categories,
        "article_type": article_type,
        "date_scraping": datetime.now(UTC).isoformat()
    }

def deduplicate_articles(articles):
    seen = set()
    unique_articles = []

    for article in articles:
        key = (
            article.get("titre", "").strip().lower(),
            article.get("source", "").strip().lower()
        )
        if key in seen:
            continue
        seen.add(key)
        unique_articles.append(article)

    return unique_articles


def save_articles_to_csv(articles, filename="articles_only_result.csv"):
    if not articles:
        return

    rows = []
    for article in articles:
        row = {k: flatten_for_csv(v) for k, v in article.items()}
        rows.append(row)

    fieldnames = list(rows[0].keys())
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(company_url, article_limit=None):
    company_info = detect_company_info(company_url)
    company_name = company_info["company_name"]

    print(f"[OK] Entreprise détectée : {company_name}")

    external_articles = []
    internal_articles = []

    try:
        external_articles = search_company_articles_gnews(company_info, max_results=50)
    except Exception as e:
        print(f"[WARN] recherche externe échouée : {e}")

    try:
        internal_articles = search_company_internal_articles(company_url, company_info, max_results=None)
    except Exception as e:
        print(f"[WARN] recherche interne échouée : {e}")

    found_articles = external_articles + internal_articles
    print(f"[OK] {len(found_articles)} article(s) trouvé(s) avant filtrage léger")

    results = []
    errors = []

    for idx, article in enumerate(found_articles, start=1):
        real_url = article["url"]
        print(f"[{idx}/{len(found_articles)}] Scraping article : {real_url}")

        try:
            scraped = extract_article_content(real_url)

            score = get_relevance_score(
                company_name,
                scraped.get("titre", ""),
                scraped.get("texte_complet", "")
            )

            scraped["relevance_score"] = score
            scraped["relevance_info"] = get_relevance_info(
                company_name,
                scraped.get("titre", ""),
                scraped.get("texte_complet", ""),
                scraped.get("source", "")
            )

            scraped["source_type"] = article.get("source_type", "unknown")
            scraped["titre_rss"] = article.get("titre_rss", "")
            scraped["date_rss"] = article.get("date_rss", "")
            scraped["source_rss"] = article.get("source_rss", "")
            results.append(scraped)

        except Exception as e:
            errors.append({
                "url": real_url,
                "titre_rss": article.get("titre_rss", ""),
                "erreur": str(e)
            })
            continue

    results = deduplicate_articles(results)
    results = sorted(results, key=lambda x: x.get("relevance_score", 0), reverse=True)

    if article_limit is not None:
        results = results[:article_limit]

    return results, errors
DB_NAME = "scraping_articles.db"


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            domain TEXT,
            company_url TEXT UNIQUE,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            titre TEXT,
            source TEXT,
            date_publication TEXT,
            url TEXT UNIQUE,
            langue TEXT,
            auteur TEXT,
            extrait TEXT,
            texte_complet TEXT,
            mots_cles TEXT,
            categories_detectees TEXT,
            article_type TEXT,
            date_scraping TEXT,
            relevance_score REAL,
            relevance_info TEXT,
            source_type TEXT,
            titre_rss TEXT,
            date_rss TEXT,
            source_rss TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
def save_company(company_info, company_url):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO companies (company_name, domain, company_url, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company_url) DO UPDATE SET
            company_name = excluded.company_name,
            domain = excluded.domain,
            description = excluded.description
    """, (
        company_info.get("company_name"),
        company_info.get("domain"),
        company_url,
        company_info.get("description")
    ))

    conn.commit()

    cursor.execute("SELECT id FROM companies WHERE company_url = ?", (company_url,))
    company_id = cursor.fetchone()[0]

    conn.close()
    return company_id
def save_articles_to_db(company_id, articles):
    conn = get_db_connection()
    cursor = conn.cursor()

    for article in articles:
        cursor.execute("""
            INSERT INTO articles (
                company_id, titre, source, date_publication, url, langue, auteur,
                extrait, texte_complet, mots_cles, categories_detectees,
                article_type, date_scraping, relevance_score, relevance_info,
                source_type, titre_rss, date_rss, source_rss
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                company_id = excluded.company_id,
                titre = excluded.titre,
                source = excluded.source,
                date_publication = excluded.date_publication,
                langue = excluded.langue,
                auteur = excluded.auteur,
                extrait = excluded.extrait,
                texte_complet = excluded.texte_complet,
                mots_cles = excluded.mots_cles,
                categories_detectees = excluded.categories_detectees,
                article_type = excluded.article_type,
                date_scraping = excluded.date_scraping,
                relevance_score = excluded.relevance_score,
                relevance_info = excluded.relevance_info,
                source_type = excluded.source_type,
                titre_rss = excluded.titre_rss,
                date_rss = excluded.date_rss,
                source_rss = excluded.source_rss
        """, (
            company_id,
            article.get("titre"),
            article.get("source"),
            article.get("date_publication"),
            article.get("url"),
            article.get("langue"),
            article.get("auteur"),
            article.get("extrait"),
            article.get("texte_complet"),
            json.dumps(article.get("mots_cles", []), ensure_ascii=False),
            json.dumps(article.get("categories_detectees", []), ensure_ascii=False),
            article.get("article_type"),
            article.get("date_scraping"),
            article.get("relevance_score"),
            json.dumps(article.get("relevance_info", {}), ensure_ascii=False),
            article.get("source_type"),
            article.get("titre_rss"),
            article.get("date_rss"),
            article.get("source_rss")
        ))

    conn.commit()
    conn.close()
    

def get_articles_by_company(company_name):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.titre, a.url, a.source, a.date_publication
        FROM articles a
        JOIN companies c ON a.company_id = c.id
        WHERE c.company_name = ?
        ORDER BY a.created_at DESC
    """, (company_name,))

    rows = cursor.fetchall()
    conn.close()
    return rows

if __name__ == "__main__":
    company_url = input("Entrez l'URL de l'entreprise : ").strip()

    try:
        init_db()

        company_info = detect_company_info(company_url)

        articles, errors = run_pipeline(company_url, article_limit=None)

        company_id = save_company(company_info, company_url)

        save_articles_to_db(company_id, articles)

        with open("articles_only_result.json", "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)

        with open("errors_result.json", "w", encoding="utf-8") as f:
            json.dump(errors, f, ensure_ascii=False, indent=4)

        save_articles_to_csv(articles, "articles_only_result.csv")

        print("\n=== ARTICLES SCRAPES ===")
        print(json.dumps(articles, ensure_ascii=False, indent=4))

        print("\n[OK] Résultats enregistrés dans :")
        print(" - articles_only_result.json")
        print(" - articles_only_result.csv")
        print(" - errors_result.json")
        print(f" - {DB_NAME}")

    except Exception as e:
        print(f"\n[ERREUR] {e}")