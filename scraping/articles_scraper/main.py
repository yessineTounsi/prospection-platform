"""
main.py — Point d'entrée du scraper modulaire.

Optimisations vitesse :
  - Scraping parallèle via ThreadPoolExecutor (SCRAPER_THREADS)
  - Timeout réduit à 10s par requête
  - Délais réduits (0.2–0.5s au lieu de 1–2s)
  - MAX_DISCOVERY_URLS = 15 (pas de marge inutile)
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config    import ARTICLE_LIMIT, DB_NAME, SCRAPER_THREADS
from company   import detect_company_info
from gnews     import search_company_articles_gnews
from discovery import discover_all_article_urls
from fetcher   import fetch_page
from extractor import is_article_page, extract_article_content
from classifier import get_relevance_score, get_relevance_info
from storage   import deduplicate_articles, save_articles_to_csv, save_articles_to_json, save_errors_to_json
from database  import init_db, save_company, save_articles_to_db


# ─────────────────────────────────────────────
#  WORKER — scrape un seul article
# ─────────────────────────────────────────────

def _scrape_one(article: dict, company_name: str) -> tuple:
    """
    Scrape un article et retourne (result_dict | None, error_dict | None).
    Conçu pour être appelé en parallèle depuis ThreadPoolExecutor.
    """
    url = article["url"]
    try:
        html = fetch_page(url)

        if not is_article_page(html, url):
            return None, None  # ignoré silencieusement

        scraped = extract_article_content(url)
        if not scraped.get("texte_complet"):
            return None, None

        scraped["relevance_score"] = get_relevance_score(
            company_name, scraped.get("titre", ""), scraped.get("texte_complet", "")
        )
        scraped["relevance_info"] = get_relevance_info(
            company_name, scraped.get("titre", ""),
            scraped.get("texte_complet", ""), scraped.get("source", "")
        )
        scraped["source_type"] = article.get("source_type", "unknown")
        scraped["titre_rss"]   = article.get("titre_rss", "")
        scraped["date_rss"]    = article.get("date_rss", "")
        scraped["source_rss"]  = article.get("source_rss", "")

        return scraped, None

    except Exception as e:
        return None, {
            "url":       url,
            "titre_rss": article.get("titre_rss", ""),
            "erreur":    str(e),
        }


# ─────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def run_pipeline(company_url: str, article_limit: int = ARTICLE_LIMIT):
    """
    Pipeline complet avec scraping parallèle.
    """
    t_start = time.time()

    # ── Étape 1 : Détection de l'entreprise
    company_info = detect_company_info(company_url)
    company_name = company_info["company_name"]
    print(f"\n[OK] Entreprise : {company_name}  (domaine : {company_info['domain']})")

    # ── Étape 2 : Articles externes via GNews
    external_articles = []
    try:
        external_articles = search_company_articles_gnews(company_info, max_results=50)
        print(f"[GNEWS] {len(external_articles)} article(s) externe(s)")
    except Exception as e:
        print(f"[WARN] GNews : {e}")

    # ── Étape 3 : Découverte des URLs internes
    internal_urls = discover_all_article_urls(company_url, company_info)
    internal_articles = [
        {
            "source_type": "company_site",
            "titre_rss": "", "url": u,
            "date_rss": "", "resume_rss": "",
            "source_rss": company_info["domain"],
        }
        for u in internal_urls
    ]

    all_candidates = external_articles + internal_articles
    print(f"\n[PIPELINE] {len(all_candidates)} article(s) à scraper en parallèle ({SCRAPER_THREADS} threads)...")

    # ── Étape 4 : Scraping PARALLÈLE ✅
    results = []
    errors  = []
    done    = 0

    with ThreadPoolExecutor(max_workers=SCRAPER_THREADS) as executor:
        futures = {
            executor.submit(_scrape_one, article, company_name): article
            for article in all_candidates
        }
        for future in as_completed(futures):
            done += 1
            article = futures[future]
            try:
                result, error = future.result()
                if result:
                    results.append(result)
                    print(f"  ✓ [{done}/{len(all_candidates)}] {article['url']}")
                elif error:
                    errors.append(error)
                    print(f"  ✗ [{done}/{len(all_candidates)}] {article['url']} — {error['erreur'][:60]}")
                else:
                    print(f"  — [{done}/{len(all_candidates)}] ignoré : {article['url']}")
            except Exception as e:
                errors.append({"url": article["url"], "erreur": str(e)})

    # ── Étape 5 : Déduplication + tri par date
    results = deduplicate_articles(results)
    results = sorted(
        results,
        key=lambda x: x.get("date_publication") or x.get("date_rss") or "",
        reverse=True,
    )

    if article_limit:
        results = results[:article_limit]

    elapsed = time.time() - t_start
    print(f"\n[TEMPS] Pipeline terminé en {elapsed:.1f}s")
    return results, errors


# ─────────────────────────────────────────────
#  POINT D'ENTRÉE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    company_url = input("Entrez l'URL de l'entreprise : ").strip()

    try:
        init_db()
        print(f"[DB] Base de données prête : {DB_NAME}")

        articles, errors = run_pipeline(company_url, article_limit=ARTICLE_LIMIT)

        company_info = detect_company_info(company_url)
        company_id   = save_company(company_info, company_url)
        save_articles_to_db(company_id, articles)
        print(f"[DB] {len(articles)} article(s) enregistré(s)")

        save_articles_to_json(articles)
        save_errors_to_json(errors)
        save_articles_to_csv(articles)

        print(f"\n{'─' * 50}")
        print(f"[RÉSULTAT] {len(articles)} article(s), {len(errors)} erreur(s)")
        print("[FICHIERS]")
        print("  - articles_only_result.json")
        print("  - articles_only_result.csv")
        print("  - errors_result.json")
        print(f"  - {DB_NAME}")
        print(f"{'─' * 50}")

    except Exception as e:
        print(f"\n[ERREUR FATALE] {e}")
        raise