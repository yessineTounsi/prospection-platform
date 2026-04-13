import re
import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("clean_internals.log", encoding="utf-8")
    ]
)

OUTPUT_JSON = "test_output_v3.json"

# Lignes à ignorer (bruit nav/CTA)
NOISE_LINES = re.compile(
    r'^(?:read more|contactdemo|contact demo|contact|demo|learn more|watch|subscribe|view blogs?|'
    r'view analyst reports?|no news available|explore vision|schedule demo|'
    r'vision journey|see what we deliver|view all stories)[\s▶]*$',
    re.IGNORECASE
)


def clean_markdown(md: str) -> str:
    """Nettoyage du markdown brut."""
    # 0. Supprimer le bloc cookie consent (très fréquent sur les sites modernes)
    md = re.sub(
        r'Customise\s+Reject All\s+Accept All.*?(?=Skip to content|Home\s|$)',
        '', md, flags=re.IGNORECASE | re.DOTALL
    )
    md = re.sub(
        r'(?:NecessaryAlways Active|Functional\s+Analytics|Performance\s+Advertisement).*?(?=\n\n|\Z)',
        '', md, flags=re.IGNORECASE | re.DOTALL
    )
    # 1. Header section scrapper2
    md = re.sub(r'^##\s+[A-Z]+\s*\n', '', md, flags=re.MULTILINE)
    # 2. Images liées [![alt](img)](url)
    md = re.sub(r'\[!\[[^\]]*\]\([^\)]+\)\]\([^\)]+\)', '', md)
    # 3. Images simples ![alt](url)
    md = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', md)
    # 4. Liens vides [](url)
    md = re.sub(r'\[\]\([^\)]+\)', '', md)
    # 5. Liens markdown → texte pur
    md = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', md)
    # 6. URLs nues
    md = re.sub(r'^\s*https?://\S+\s*$', '', md, flags=re.MULTILINE)
    # 7. Footer nav bloc
    md = re.sub(
        r'###\s+(?:SERVICES|VISION|EXPERIENCE|COMPANY|CONTACT|ABOUT).*',
        '', md, flags=re.IGNORECASE | re.DOTALL
    )
    # 8. Lignes footer légal
    lines = md.split('\n')
    lines = [l for l in lines if not re.search(
        r'confidentiality|terms|cookies|all rights reserved|©|\bprivacy\b',
        l, re.IGNORECASE
    )]
    # 9. Lignes nav répétitives
    NAV = re.compile(
        r'^(?:\s*(?:Services|Industries|Customers|Partners|Company|Vision Journey)\s*[>\|]?\s*)+$',
        re.IGNORECASE
    )
    lines = [l for l in lines if not NAV.match(l.strip())]
    md = '\n'.join(lines)
    # 10. Nettoyer espaces
    md = re.sub(r'[ \t]+', ' ', md)
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def extract_paragraphs(clean_md: str) -> list:
    """
    Extrait les paragraphes en respectant les sections H3 comme séparateurs.
    Fusionne les stats (5+ → Years Experience).
    """
    # Fusionner stats chiffres
    clean_md = re.sub(r'(\d+\+?)\s*\n\s*([A-Za-z][^\n]{2,40})', r'\1 \2', clean_md)

    # Séparer par blocs vides OU par headings H3/H4
    blocks = re.split(r'\n\n+|\n(?=#{3,4}\s)', clean_md)

    paragraphs = []
    for block in blocks:
        block = block.strip()
        # Supprimer marqueurs titres
        block = re.sub(r'^#{1,4}\s+', '', block, flags=re.MULTILINE)
        # Supprimer séparateurs * * *
        block = re.sub(r'^\s*\*\s*\*\s*\*\s*$', '', block, flags=re.MULTILINE)
        # Joindre lignes
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        # Filtrer lignes bruit
        lines = [l for l in lines if not NOISE_LINES.match(l)]
        block = ' '.join(lines)
        if len(block) >= 5:
            paragraphs.append(block)

    return paragraphs


def extract_clean_text(clean_md: str) -> str:
    """Texte brut complet pour le NLP."""
    clean_md = re.sub(r'(\d+\+?)\s*\n\s*([A-Za-z][^\n]{2,40})', r'\1 \2', clean_md)
    text = re.sub(r'^#{1,4}\s+', '', clean_md, flags=re.MULTILINE)
    text = re.sub(r'[\*\_`]', '', text)
    # Filtrer lignes bruit
    lines = [l for l in text.split('\n') if l.strip() and not NOISE_LINES.match(l.strip())]
    text = ' '.join(lines)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def process_secondary_pages(company: dict) -> dict:
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
        logging.info(f"  ✅ [{page_name}] {len(secondary_data[page_name]['paragraphs'])} paragraphes")

    company["secondary_data"] = secondary_data
    return company


def main():
    input_path = Path(input("📂 Chemin du fichier JSON (v2) : ").strip())
    if not input_path.exists():
        print(f"❌ Fichier introuvable : {input_path}")
        return
    with open(input_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    if isinstance(dataset, dict):
        dataset = [dataset]
    enriched = [process_secondary_pages(c) for c in dataset]
    output_path = input_path.parent / OUTPUT_JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=4, ensure_ascii=False)
    print(f"✅ Sauvegardé : {output_path}")

if __name__ == "__main__":
    main()