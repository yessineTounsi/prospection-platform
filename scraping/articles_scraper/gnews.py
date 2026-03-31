import time
from urllib.parse import quote

from config import API_KEY, REQUEST_TIMEOUT, session


# ─────────────────────────────────────────────
#  GNEWS — ARTICLES EXTERNES
# ─────────────────────────────────────────────

def search_company_articles_gnews(company_info: dict, max_results: int = 50) -> list:
    """
    Interroge l'API GNews pour récupérer des articles de presse externes
    mentionnant l'entreprise (via ses alias).

    Retourne une liste de dicts standardisés avec les champs :
        source_type, titre_rss, url, date_rss, resume_rss, source_rss
    """
    aliases  = company_info.get("aliases", [])
    queries  = []
    for alias in aliases:
        queries.append(f'"{alias}"')
        queries.append(f'"{alias}" news')

    all_articles = []
    seen_urls    = set()

    for query in queries:
        time.sleep(2)
        api_url = (
            f"https://gnews.io/api/v4/search?"
            f"q={quote(query)}&lang=en&max={max_results}&apikey={API_KEY}"
        )
        try:
            response = session.get(api_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()

            for item in data.get("articles", []):
                article_url = item.get("url", "")
                if not article_url or article_url in seen_urls:
                    continue
                seen_urls.add(article_url)
                all_articles.append({
                    "source_type": "external_news",
                    "titre_rss":   item.get("title", ""),
                    "url":         article_url,
                    "date_rss":    item.get("publishedAt", ""),
                    "resume_rss":  item.get("description", ""),
                    "source_rss":  item.get("source", {}).get("name", ""),
                })

        except Exception as e:
            print(f"[WARN] GNews query '{query}' échouée : {e}")
            continue

    return all_articles