"""
main.py — Point d'entrée du scraper modulaire.

Amélioration : logs détaillés montrant exactement pourquoi
chaque article candidat est accepté, ignoré ou en erreur.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config    import ARTICLE_LIMIT, DB_NAME, SCRAPER_THREADS
# ── Import du cleaner depuis son dossier (Cleaning/)
import importlib.util, os as _os

_cleaner_path = _os.path.join(_os.path.dirname(__file__), '..', '..', 'Cleaning', 'cleaner.py')
_spec         = importlib.util.spec_from_file_location("cleaner", _cleaner_path)
_cleaner_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cleaner_mod)
run_cleaning_pipeline = _cleaner_mod.run_cleaning_pipeline
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
    Scrape un article.
    Retourne (result | None, error | None, skip_reason | None)
    """
    url = article["url"]
    try:
        html = fetch_page(url)

        if not is_article_page(html, url):
            return None, None, "pas un article"

        scraped = extract_article_content(url)

        if not scraped.get("texte_complet"):
            return None, None, "texte vide"

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

        return scraped, None, None

    except Exception as e:
        return None, {
            "url":       url,
            "titre_rss": article.get("titre_rss", ""),
            "erreur":    str(e),
        }, None


# ─────────────────────────────────────────────
#  PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def run_pipeline(company_url: str, article_limit: int = ARTICLE_LIMIT):
    t_start = time.time()

    # ── Étape 1 : Détection de l'entreprise
    company_info = detect_company_info(company_url)
    company_name = company_info["company_name"]
    print(f"\n[OK] Entreprise : {company_name}")

    # ── Étape 2 : Articles externes via GNews
    external_articles = []
    try:
        external_articles = search_company_articles_gnews(company_info)
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
    total = len(all_candidates)
    print(f"\n[PIPELINE] {total} URL(s) candidate(s) → scraping en parallèle ({SCRAPER_THREADS} threads)")
    print(f"{'─' * 60}")

    # ── Étape 4 : Scraping parallèle
    results      = []
    errors       = []
    skipped      = []
    done         = 0

    # Compteurs détaillés
    count_ok         = 0
    count_not_article = 0
    count_empty_text  = 0
    count_error       = 0

    with ThreadPoolExecutor(max_workers=SCRAPER_THREADS) as executor:
        futures = {
            executor.submit(_scrape_one, article, company_name): article
            for article in all_candidates
        }
        for future in as_completed(futures):
            done += 1
            article = futures[future]
            url     = article["url"]

            try:
                result, error, skip_reason = future.result()

                if result:
                    results.append(result)
                    count_ok += 1
                    print(f"  ✓ [{done}/{total}] {url[:70]}")

                    # ✅ Arrêt anticipé dès qu'on a assez d'articles
                    if len(results) >= article_limit:
                        print(f"  ✓ Limite de {article_limit} articles atteinte — arrêt anticipé")
                        break

                elif error:
                    errors.append(error)
                    count_error += 1
                    print(f"  ✗ [{done}/{total}] ERREUR  — {url[:60]}")
                    print(f"       └ {error['erreur'][:80]}")

                elif skip_reason == "pas un article":
                    count_not_article += 1
                    skipped.append({"url": url, "raison": skip_reason})
                    print(f"  — [{done}/{total}] IGNORÉ (pas un article) — {url[:60]}")

                elif skip_reason == "texte vide":
                    count_empty_text += 1
                    skipped.append({"url": url, "raison": skip_reason})
                    print(f"  — [{done}/{total}] IGNORÉ (texte vide)     — {url[:60]}")

            except Exception as e:
                errors.append({"url": url, "erreur": str(e)})
                count_error += 1

    # ── Étape 5 : Déduplication
    before_dedup = len(results)
    results      = deduplicate_articles(results)
    count_dedup  = before_dedup - len(results)

    # ── Étape 6 : Tri par date
    results = sorted(
        results,
        key=lambda x: x.get("date_publication") or x.get("date_rss") or "",
        reverse=True,
    )

    # ── Étape 7 : Limite finale
    before_limit = len(results)
    if article_limit:
        results = results[:article_limit]
    count_limit = before_limit - len(results)

    elapsed = time.time() - t_start

    # ── Rapport détaillé
    print(f"\n{'─' * 60}")
    print(f"[RAPPORT] Pipeline terminé en {elapsed:.1f}s")
    print(f"{'─' * 60}")
    print(f"  Candidats total       : {total}")
    print(f"  ✓ Scrapés avec succès : {count_ok}")
    print(f"  — Ignorés (pas article): {count_not_article}")
    print(f"  — Ignorés (texte vide) : {count_empty_text}")
    print(f"  ✗ Erreurs             : {count_error}")
    if count_dedup > 0:
        print(f"  ~ Doublons supprimés  : {count_dedup}")
    if count_limit > 0:
        print(f"  ↓ Coupés par limite   : {count_limit} (limite={article_limit})")
    print(f"{'─' * 60}")
    print(f"  ➜ RÉSULTAT FINAL      : {len(results)} article(s)")
    print(f"{'─' * 60}")

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

        print(f"\n[FICHIERS]")
        print(f"  - articles_only_result.json  ({len(articles)} articles)")
        print(f"  - articles_only_result.csv")
        print(f"  - errors_result.json         ({len(errors)} erreurs)")
        print(f"  - {DB_NAME}")

        # ── Nettoyage automatique pour NLP
        print(f"\n[CLEANER] Nettoyage automatique des résultats...")
        run_cleaning_pipeline(
            input_path   = "articles_only_result.json",
            output_json  = "articles_cleaned.json",
            output_csv   = "articles_cleaned.csv",
            company_name = company_info.get("company_name", ""),
        )

    except Exception as e:
        print(f"\n[ERREUR FATALE] {e}")
        raise