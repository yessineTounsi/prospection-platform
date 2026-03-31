import csv
import json

from utils import flatten_for_csv


# ─────────────────────────────────────────────
#  DÉDUPLICATION
# ─────────────────────────────────────────────

def deduplicate_articles(articles: list) -> list:
    """
    Supprime les doublons en se basant sur le couple (titre normalisé, source).
    Conserve la première occurrence.
    """
    seen   = set()
    unique = []
    for article in articles:
        key = (
            article.get("titre", "").strip().lower(),
            article.get("source", "").strip().lower(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


# ─────────────────────────────────────────────
#  SAUVEGARDE CSV
# ─────────────────────────────────────────────

def save_articles_to_csv(articles: list, filename: str = "articles_only_result.csv"):
    """
    Écrit les articles dans un fichier CSV UTF-8.
    Les listes et dicts sont sérialisés en chaînes lisibles.
    """
    if not articles:
        print("[WARN] Aucun article à écrire dans le CSV.")
        return

    rows = [{k: flatten_for_csv(v) for k, v in a.items()} for a in articles]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] CSV enregistré : {filename}")


# ─────────────────────────────────────────────
#  SAUVEGARDE JSON
# ─────────────────────────────────────────────

def save_articles_to_json(articles: list, filename: str = "articles_only_result.json"):
    """Écrit les articles dans un fichier JSON indenté UTF-8."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=4)
    print(f"[OK] JSON enregistré : {filename}")


def save_errors_to_json(errors: list, filename: str = "errors_result.json"):
    """Écrit les erreurs de scraping dans un fichier JSON."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=4)
    print(f"[OK] Erreurs enregistrées : {filename}")