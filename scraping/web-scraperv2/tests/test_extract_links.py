"""
test_extract_links.py — Extrait et score les liens internes d'un fichier .md
Dossier : tests/

Usage :
    python tests/test_extract_links.py output/md/www_biat_com_tn.md
    python tests/test_extract_links.py output/md/
"""

import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from navigation.link_extractor import extract_links
from navigation.link_scorer import LinkScorer, scored_links_to_rich_dict


def guess_base_url(md_path):
    content = md_path.read_text(encoding='utf-8', errors='ignore')
    pattern = re.compile(r'https?://[a-zA-Z0-9.\-]+\.[a-z]{2,}')
    matches = pattern.findall(content)
    if not matches:
        return None
    domain_count = {}
    for url in matches:
        try:
            domain = re.match(r'https?://([^/]+)', url).group(1)
            domain_count[domain] = domain_count.get(domain, 0) + 1
        except:
            continue
    main_domain = max(domain_count, key=domain_count.get)
    schema = 'https' if 'https://' + main_domain in content else 'http'
    return schema + '://' + main_domain


def process_file(md_path, base_url, scorer):
    content = md_path.read_text(encoding='utf-8', errors='ignore')
    sep = '-' * 65

    print(sep)
    print('FILE     : ' + md_path.name)
    print('BASE URL : ' + str(base_url))

    links = extract_links(content, base_url=base_url)
    print('Liens internes retenus : ' + str(len(links)))

    if not links:
        print('Aucun lien interne trouve.')
        return

    print('')
    print('Liens candidats au scoring :')
    for i, l in enumerate(links, 1):
        print('  ' + str(i).zfill(2) + '. ' + repr(l.text) + ' -> ' + l.url)

    print('')
    print('Scoring en cours...')
    results = scorer.score_links(links, top_k=7, max_per_cat=1)
    rich    = scored_links_to_rich_dict(results)

    if not rich:
        print('Aucune page retenue par le scorer.')
        return

    print('')
    print('Pages selectionnees pour scraping (' + str(len(rich)) + ') :')
    for cat, data in rich.items():
        print('  [' + cat + '] score=' + str(data['score']) + '  ' + data['url'])
        print('         text=' + repr(data['link_text']))


def main():
    args = sys.argv[1:]

    if not args:
        print('Usage :')
        print('  python tests/test_extract_links.py output/md/fichier.md')
        print('  python tests/test_extract_links.py output/md/')
        sys.exit(0)

    target = Path(args[0])
    explicit_base_url = args[1] if len(args) > 1 else None

    print('Chargement du scorer...')
    scorer = LinkScorer()
    print('Scorer pret.')
    print('')

    if target.is_file():
        base_url = explicit_base_url or guess_base_url(target)
        process_file(target, base_url, scorer)

    elif target.is_dir():
        files = sorted(target.glob('*.md'))
        print(str(len(files)) + ' fichiers trouves dans ' + str(target))
        for f in files:
            base_url = guess_base_url(f)
            if not base_url:
                print('SKIP ' + f.name + ' base_url introuvable')
                continue
            process_file(f, base_url, scorer)
    else:
        print('Introuvable : ' + str(target))
        sys.exit(1)


if __name__ == '__main__':
    main()