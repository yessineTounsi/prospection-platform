import sys
from pathlib import Path
# Permet dimporter les modules depuis la racine du projet
sys.path.insert(0, str(Path(__file__).parent.parent))
"""
test_scorer_on_md.py — Teste le link scorer sur les fichiers .md reels
Usage : python test_scorer_on_md.py
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from navigation.link_extractor import extract_links
from navigation.link_scorer    import LinkScorer, scored_links_to_rich_dict

MD_DIR = Path(__file__).parent.parent / "output" / "md"

def filename_to_baseurl(filename: str) -> str:
    name  = filename.replace(".md", "").rstrip("_")
    parts = name.split("_")
    TLDS  = {"com", "tn", "fr", "net", "org", "ai", "tech", "io"}
    result = []
    for i, part in enumerate(parts):
        result.append(part)
        if part.lower() in TLDS:
            remaining = parts[i+1:]
            if remaining:
                return "https://" + ".".join(result) + "/" + "/".join(remaining)
            return "https://" + ".".join(result)
    return "https://" + ".".join(result)


def test_file(md_path: Path, scorer: LinkScorer) -> dict:
    base_url = filename_to_baseurl(md_path.stem)
    with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
        markdown = f.read()
    links   = extract_links(markdown, base_url=base_url)
    results = scorer.score_links(links, top_k=7, max_per_cat=1)
    return {
        "file":        md_path.name,
        "base_url":    base_url,
        "total_links": len(links),
        "selected":    len(results),
        "navigation":  scored_links_to_rich_dict(results),
    }


def main():
    md_files = sorted(MD_DIR.glob("*.md"))
    if not md_files:
        print(f"Aucun fichier .md trouve dans {MD_DIR}")
        sys.exit(1)

    print(f"
Chargement du modele...")
    scorer = LinkScorer()
    print(f"Modele pret — {len(md_files)} fichiers
")

    all_results = []
    for md_path in md_files:
        try:
            r = test_file(md_path, scorer)
            all_results.append(r)

            print(f"{'─'*60}")
            print(f"FILE     : {r['file']}")
            print(f"LIENS    : {r['total_links']} apres blacklist  →  {r['selected']} retenus")

            if not r["navigation"]:
                print(f"RESULTAT : aucun lien retenu")
            else:
                for cat, data in r["navigation"].items():
                    print(f"  [{cat:<12}] score={data['score']:.3f}  {data['url']}")
                    print(f"  {'':14}  text={data['link_text']!r}")

        except Exception as e:
            print(f"ERREUR sur {md_path.name} : {e}")

    # Recap
    print(f"
{'='*60}")
    print(f"RECAP")
    cats_found = {}
    empty = 0
    for r in all_results:
        if not r["navigation"]:
            empty += 1
            continue
        for cat in r["navigation"]:
            cats_found[cat] = cats_found.get(cat, 0) + 1

    print(f"Traites : {len(all_results)}  |  Sans resultat : {empty}  |  Avec resultats : {len(all_results)-empty}")
    print(f"
Categories trouvees :")
    for cat, count in sorted(cats_found.items(), key=lambda x: -x[1]):
        print(f"  {cat:<14} {count}/{len(all_results)}")

    if empty:
        print(f"
Fichiers sans resultat :")
        for r in all_results:
            if not r["navigation"]:
                print(f"  - {r['file']}")
    print()


if __name__ == "__main__":
    main()
