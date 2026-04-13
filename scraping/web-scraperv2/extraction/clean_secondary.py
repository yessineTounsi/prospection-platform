"""
extraction/clean_secondary.py — Nettoyage des pages internes scrapees
======================================================================
Prend les secondary_pages brutes (markdown) produites par scraper2
et les transforme en donnees structurees utilisables pour :
  - L enrichissement NLP (company_name, description, services...)
  - L indexation Elasticsearch
  - Le stockage MongoDB

Input  : company["secondary_pages"] = {categorie: markdown_brut | "failed"}
Output : company["secondary_data"]  = {categorie: {clean_text, paragraphs}}
"""

import logging
from extraction.clean_internals import clean_markdown, extract_paragraphs, extract_clean_text

logger = logging.getLogger(__name__)


def process_secondary_pages(company: dict) -> dict:
    """
    Nettoie et structure chaque page interne scrapee.

    Pour chaque page :
      1. Nettoie le markdown (supprime images, liens, nav, footer legal)
      2. Extrait le texte brut continu (clean_text) pour le NLP
      3. Segmente en paragraphes structures (paragraphs) pour l indexation

    Args:
        company : Dict entreprise avec secondary_pages rempli par scraper2

    Returns:
        company enrichi avec secondary_data :
        {
            "about": {
                "clean_text": "Fondee en 1990, la BIAT est...",
                "paragraphs": ["Fondee en 1990...", "Notre mission est..."]
            },
            "team": { ... },
            "services": "failed"  # si le scraping a echoue
        }
    """
    secondary_pages = company.get("secondary_pages", {})
    if not secondary_pages:
        return company

    secondary_data = {}

    for page_name, markdown in secondary_pages.items():

        # Page non scrapee
        if markdown == "failed" or not markdown:
            secondary_data[page_name] = "failed"
            continue

        # Nettoyer le markdown
        clean_md = clean_markdown(markdown)
        if len(clean_md.strip()) < 50:
            secondary_data[page_name] = "failed"
            logger.warning("  [" + page_name + "] Contenu trop court apres nettoyage")
            continue

        # Extraire texte et paragraphes
        clean_text = extract_clean_text(clean_md)
        paragraphs = extract_paragraphs(clean_md)

        secondary_data[page_name] = {
            "clean_text": clean_text,
            "paragraphs": paragraphs,
        }
        logger.info("  [" + page_name + "] " + str(len(paragraphs)) + " paragraphes")

    company["secondary_data"] = secondary_data
    return company