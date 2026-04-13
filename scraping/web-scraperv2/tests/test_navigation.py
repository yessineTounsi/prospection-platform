import sys
from pathlib import Path
# Permet dimporter les modules depuis la racine du projet
sys.path.insert(0, str(Path(__file__).parent.parent))
"""
test_navigation.py — Test sur 20 liens realistes d'un cabinet de consulting IT
"""

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from navigation.link_extractor import extract_links
from navigation.link_scorer    import LinkScorer, scored_links_to_rich_dict

# ── 20 liens typiques d'un site consulting IT (FR + EN mix) ──────────────────
# Cas realiste : navigation principale + footer + pages metier
MARKDOWN_CONSULTING_IT = """
# TechConsult — Votre partenaire transformation digitale

Navigation principale :
[Accueil](https://techconsult.fr)
[Qui sommes-nous](https://techconsult.fr/qui-sommes-nous)
[Notre equipe dirigeante](https://techconsult.fr/equipe-direction)
[Nos expertises](https://techconsult.fr/expertises)
[Conseil en transformation digitale](https://techconsult.fr/expertises/conseil-transformation-digitale)
[Integration de systemes](https://techconsult.fr/expertises/integration-systemes)
[Cybersecurite](https://techconsult.fr/expertises/cybersecurite)
[Cloud & Infrastructure](https://techconsult.fr/expertises/cloud-infrastructure)
[Nos references clients](https://techconsult.fr/references-clients)
[Etudes de cas](https://techconsult.fr/etudes-de-cas)

Pages metier :
[Notre methodologie](https://techconsult.fr/methodologie)
[Nos technologies partenaires](https://techconsult.fr/technologies-partenaires)
[Actualites et insights](https://techconsult.fr/actualites)
[Nous contacter](https://techconsult.fr/contact)
[Nos bureaux](https://techconsult.fr/nos-bureaux)

Footer - liens utiles :
[Mentions legales](https://techconsult.fr/mentions-legales)
[Politique de confidentialite](https://techconsult.fr/confidentialite)
[Offres d emploi](https://techconsult.fr/carrieres)
[Service support client](https://techconsult.fr/support)
[Plan du site](https://techconsult.fr/sitemap)
"""

def run_test(name: str, markdown: str, base_url: str, scorer: LinkScorer):
    print(f"
{'='*65}")
    print(f"TEST : {name}")
    print(f"{'='*65}")

    links = extract_links(markdown, base_url=base_url)

    print(f"
{len(links)} liens retenus apres blacklist (sur 20 extraits) :")
    for l in links:
        print(f"  text={l.text!r:<45} slug={l.url_slug!r}")

    print(f"
--- Scoring ---")
    results = scorer.score_links(links, top_k=7, max_per_cat=1)

    print(f"
Top {len(results)} liens selectionnes :")
    for r in results:
        print(f"  [{r.category:<12}] score={r.score:.3f}  {r.link.url}")
        print(f"               text={r.link.text!r}")

    print(f"
Bundle final (format MongoDB) :")
    rich = scored_links_to_rich_dict(results)
    for cat, data in rich.items():
        print(f"  {cat:<12} → {data['url']}")
        print(f"               score={data['score']}  text={data['link_text']!r}")

    # Verification des rejets
    all_extracted = extract_links(markdown, base_url=base_url, internal_only=False)
    print(f"
Verification blacklist :")
    expected_rejected = [
        'mentions-legales', 'confidentialite', 'carrieres', 'support', 'sitemap'
    ]
    for slug in expected_rejected:
        found = any(slug in l.url for l in links)
        status = "ERREUR - pas rejete" if found else "OK - bien rejete"
        print(f"  /{slug:<30} → {status}")


def main():
    print("Chargement du modele sentence-transformers...")
    scorer = LinkScorer()

    run_test(
        name     = "Cabinet Consulting IT - 20 liens FR",
        markdown = MARKDOWN_CONSULTING_IT,
        base_url = "https://techconsult.fr",
        scorer   = scorer,
    )

    print(f"
{'='*65}")
    print("Tests termines.")
    print("Verifie que :")
    print("  - Les 5 liens footer sont bien rejetes par la blacklist")
    print("  - about / team / services / contact / clients / technology")
    print("    matchent les bonnes URLs")
    print("  - Les sous-pages metier (cybersecurite, cloud...) sont bien")
    print("    classees dans 'services' ou 'technology'")
    print(f"{'='*65}
")


if __name__ == "__main__":
    main()
