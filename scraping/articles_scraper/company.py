from bs4 import BeautifulSoup
from urllib.parse import urlparse

from fetcher import fetch_page
from utils import clean_text, extract_meta


# ─────────────────────────────────────────────
#  DÉTECTION DE L'ENTREPRISE
# ─────────────────────────────────────────────

def normalize_company_name(name: str) -> str:
    """
    Nettoie un nom d'entreprise extrait d'un <title> ou d'une balise meta :
    - Supprime les suffixes type "| Accueil", "- Site officiel"
    - Rejette les noms génériques trop courts
    """
    if not name:
        return ""
    name = clean_text(name)
    for sep in ["|", " - ", " — ", ":", "•"]:
        if sep in name:
            parts = [clean_text(p) for p in name.split(sep) if clean_text(p)]
            if parts:
                name = parts[0]
                break
    generic_names = {"home", "welcome", "official site", "homepage", "website", "site", "blog", "news"}
    if len(name) < 3 or name.lower() in generic_names:
        return ""
    return name


def domain_to_company_name(domain: str) -> str:
    """Convertit un domaine (ex: my-company.com) en nom lisible (My Company)."""
    base = domain.split(".")[0]
    base = base.replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in base.split())


def detect_company_info(company_url: str) -> dict:
    """
    Détecte automatiquement le nom, le domaine et la description
    d'une entreprise à partir de son URL.

    Retourne :
        {
            "company_name": str,
            "domain": str,
            "aliases": list[str],
            "description": str
        }
    """
    html = fetch_page(company_url, use_dynamic_fallback=True)
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(company_url).netloc.replace("www.", "")

    title     = clean_text(soup.title.get_text()) if soup.title else ""
    og_title  = extract_meta(soup, "property", "og:title")
    site_name = extract_meta(soup, "property", "og:site_name")
    description = (
        extract_meta(soup, "name", "description") or
        extract_meta(soup, "property", "og:description")
    )
    h1      = soup.find("h1")
    h1_text = clean_text(h1.get_text()) if h1 else ""

    candidates = [
        normalize_company_name(site_name),
        normalize_company_name(title),
        normalize_company_name(og_title),
        normalize_company_name(h1_text),
        domain_to_company_name(domain),
    ]
    company_name = next((c for c in candidates if c), "")

    aliases = {company_name, domain.split(".")[0], domain_to_company_name(domain)}
    aliases = {clean_text(a) for a in aliases if a and len(a) >= 2}

    return {
        "company_name": company_name,
        "domain": domain,
        "aliases": list(aliases),
        "description": description,
    }