"""
clean_secondary.py — Nettoie les secondary_pages du scrapper 2
Produit secondary_data avec clean_text + paragraphs pour le NLP
"""
import logging
from .clean_internals import clean_markdown, extract_paragraphs, extract_clean_text

logger = logging.getLogger(__name__)


def process_secondary_pages(company: dict) -> dict:
    """
    Pour chaque secondary_page → nettoie + extrait clean_text + paragraphs
    Résultat dans company["secondary_data"]
    """
    secondary_pages = company.get("secondary_pages", {})
    if not secondary_pages:
        return company

    secondary_data = {}

    for page_name, markdown in secondary_pages.items():
        if markdown == "failed" or not markdown:
            secondary_data[page_name] = "failed"
            continue

        clean_md = clean_markdown(markdown)
        if len(clean_md.strip()) < 50:
            secondary_data[page_name] = "failed"
            continue

        secondary_data[page_name] = {
            "clean_text": extract_clean_text(clean_md),
            "paragraphs": extract_paragraphs(clean_md),
        }
        logger.info(f"  ✅ [{page_name}] {len(secondary_data[page_name]['paragraphs'])} paragraphes")

    company["secondary_data"] = secondary_data
    return company