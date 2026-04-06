"""
main.py — Point d'entrée du Trustpilot Scraper
===============================================
Installation :
    pip install requests beautifulsoup4

Lancement :
    python main.py

Structure du projet :
    main.py       ← ce fichier (orchestre tout)
    config.py     ← headers HTTP + NB_COMMENTAIRES
    fetcher.py    ← fetch HTTP, recherche, choix entreprise
    parsers.py    ← scrape score, résumé IA, commentaires
    display.py    ← affichage terminal + sauvegarde JSON/CSV
"""

from config  import NB_COMMENTAIRES
from fetcher import fetch_page, rechercher_entreprise, choisir_entreprise
from parsers import scrape_score, scrape_resume, scrape_commentaires
from display import afficher_resultats, save_results


def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║         TRUSTPILOT SCRAPER  —  recherche par nom          ║")
    print("╚════════════════════════════════════════════════════════════╝")

    while True:
        nom = input("\n  Nom de l'entreprise (ou 'quitter') : ").strip()

        if nom.lower() in ("quitter", "quit", "q", "exit"):
            print("\n  Au revoir ! 👋\n")
            break

        if not nom:
            print("  ⚠  Merci d'entrer un nom.")
            continue

        # 1 — Recherche + choix
        resultats = rechercher_entreprise(nom)
        if not resultats:
            print(f"\n  ✗  Aucun résultat pour '{nom}'.")
            continue

        entreprise = choisir_entreprise(resultats)
        if not entreprise:
            continue

        print(f"\n  ✅  {entreprise['nom']}  —  {entreprise['url']}")
        print(f"  📥  Chargement de la page…")

        # 2 — Téléchargement
        soup = fetch_page(entreprise["url"])
        if not soup:
            print("  ✗  Impossible de charger la page.")
            continue

        # 3 — Extraction
        print("  ⚙   Score + distribution étoiles…")
        score = scrape_score(soup)

        print("  ⚙   Résumé IA…")
        resume = scrape_resume(soup)

        print("  ⚙   Commentaires…")
        commentaires = scrape_commentaires(soup, nb=NB_COMMENTAIRES)

        # 4 — Affichage + sauvegarde
        afficher_resultats(entreprise, score, resume, commentaires)
        save_results(entreprise, score, resume, commentaires)

        # 5 — Continuer ?
        again = input("\n  Scraper une autre entreprise ? [O/n] : ").strip().lower()
        if again in ("n", "non", "no"):
            print("\n  Au revoir ! 👋\n")
            break


if __name__ == "__main__":
    main()