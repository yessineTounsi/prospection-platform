"""
md_to_json.py — Convertit un fichier .md en JSON structuré
Extrait les champs regex + welcome_data (paragraphes propres)
"""
import os
import logging
from pathlib import Path

from .extractors import (
    extract_email, extract_phone, extract_linkedin,
    extract_website_url, extract_logo, extract_address,
    extract_country, extract_internal_urls
)
from .clean_internals import clean_markdown, extract_paragraphs, extract_clean_text

logger = logging.getLogger(__name__)


def process_markdown(file_path: str | Path) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        md = f.read()

    filename    = os.path.basename(file_path)
    website_url = extract_website_url(md, filename)

    clean_md    = clean_markdown(md)
    welcome_data = {
        "clean_text": extract_clean_text(clean_md),
        "paragraphs": extract_paragraphs(clean_md),
    }

    logger.info(f"  ✅ {filename} — {website_url} — {len(welcome_data['paragraphs'])} paragraphes welcome")

    return {
        "source_file":      filename,
        "website_url":      website_url,
        "logo_url":         extract_logo(md),
        "linkedin":         extract_linkedin(md),
        "email":            extract_email(md),
        "phone":            extract_phone(md),
        "address":          extract_address(md),
        "country":          extract_country(md),
        "internal_urls":    extract_internal_urls(md, website_url),
        "welcome_data":     welcome_data,
        "company_name":     None,
        "description":      None,
        "services":         None,
        "clients":          None,
        "team_leaders":     None,
        "founded_year":     None,
        "employees_count":  None,
        "revenue":          None,
        "reviews":          None,
        "raw_markdown":     md,
    }