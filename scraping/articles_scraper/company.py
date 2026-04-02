from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from urllib.parse import urlparse

from fetcher import fetch_page
from utils import clean_text, extract_meta


# ─────────────────────────────────────────────
#  DÉTECTION DE L'ENTREPRISE
# ─────────────────────────────────────────────

def normalize_company_name(name: str) -> str:
    """
    Nettoie un nom d'entreprise extrait d'un <title> ou d'une balise meta.
    Supprime les suffixes type "| Accueil", rejette les noms génériques.
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
    generic_names = {"home", "welcome", "official site", "homepage",
                     "website", "site", "blog", "news"}
    if len(name) < 3 or name.lower() in generic_names:
        return ""
    return name


def domain_to_company_name(domain: str) -> str:
    """Convertit un domaine (ex: my-company.com) en nom lisible (My Company)."""
    base = domain.split(".")[0]
    base = base.replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in base.split())


def _build_fallback_info(domain: str, description: str = "") -> dict:
    """Construit les infos de base depuis le domaine quand le site est inaccessible."""
    company_name = domain_to_company_name(domain)
    aliases = {company_name, domain.split(".")[0], domain_to_company_name(domain)}
    aliases = {clean_text(a) for a in aliases if a and len(a) >= 2}
    return {
        "company_name": company_name,
        "domain": domain,
        "aliases": list(aliases),
        "description": description,
    }


def detect_company_info(company_url: str) -> dict:
    """
    Détecte automatiquement le nom, le domaine et la description
    d'une entreprise à partir de son URL.

    Si la homepage est inaccessible (anti-bot, Cloudflare...),
    utilise le domaine comme fallback et continue le pipeline
    sans crasher — la découverte via paths hardcodés prendra le relais.
    """
    domain = urlparse(company_url).netloc.replace("www.", "")

    # Tentative de fetch de la homepage
    try:
        html = fetch_page(company_url, use_dynamic_fallback=True)   # Playwright pour sites JS
    except Exception:

        return _build_fallback_info(domain)

    soup = BeautifulSoup(html, "html.parser")

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
    company_name = next((c for c in candidates if c), domain_to_company_name(domain))

    # Si le nom détecté ressemble à un slogan (trop long, pas de majuscule initiale seule)
    # → utilise le domaine comme nom plus fiable
    domain_name = domain_to_company_name(domain)
    if (len(company_name.split()) > 4 or
        company_name.lower() == company_name or
        len(company_name) > 50):
        company_name = domain_name

    aliases = {company_name, domain.split(".")[0], domain_to_company_name(domain)}
    aliases = {clean_text(a) for a in aliases if a and len(a) >= 2}

    return {
        "company_name": company_name,
        "domain": domain,
        "aliases": list(aliases),
        "description": description,
    }