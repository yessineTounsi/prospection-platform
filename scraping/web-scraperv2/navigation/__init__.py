"""
navigation/ — Module de scoring sémantique des liens internes

Usage rapide :
    from navigation import LinkScorer, extract_links, scored_links_to_rich_dict

    scorer  = LinkScorer()   # charger une fois pour tout le batch

    links   = extract_links(markdown, base_url="https://acme.com")
    results = scorer.score_links(links)
    nav     = scored_links_to_rich_dict(results)
"""

from navigation.link_extractor import extract_links, extract_links_from_bundle, ExtractedLink
from navigation.link_scorer    import LinkScorer, score_links, scored_links_to_dict, scored_links_to_rich_dict
from navigation.categories     import CATEGORIES, CATEGORIES_BY_NAME, SCORER_CONFIG

__all__ = [
    "extract_links",
    "extract_links_from_bundle",
    "ExtractedLink",
    "LinkScorer",
    "score_links",
    "scored_links_to_dict",
    "scored_links_to_rich_dict",
    "CATEGORIES",
    "CATEGORIES_BY_NAME",
    "SCORER_CONFIG",
]
