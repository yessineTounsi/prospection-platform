"""
extraction/nlp_enricher.py — Phase 7 : Enrichissement NLP (spaCy)
==================================================================
Utilise spaCy pour extraire des informations supplémentaires à partir
du texte scrapé B2B.

Champs null remplis si trouvés :
  team_leaders     — PERSON + titre détecté dans le contexte
  reviews          — citations textuelles avec attribution
  founded_year     — année de fondation
  employees_count  — effectif

Nouveaux champs ajoutés :
  key_metrics      — chiffres clés ("30+ years", "160+ clients"...)
  certifications   — ISO, SOC, SWIFT, PCI-DSS...
  technologies     — outils / frameworks mentionnés
  sectors          — secteurs d'activité identifiés
  locations_geo    — villes / pays où l'entreprise est présente
  orgs_mentioned   — organisations tierces détectées (clients potentiels)

Installation :
    pip install spacy
    python -m spacy download en_core_web_lg
    python -m spacy download fr_core_news_lg   # optionnel, pour contenu FR
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Chargement spaCy ───────────────────────────────────────────────────────────

try:
    import spacy
    _nlp_en = _nlp_fr = None

    for model in ("en_core_web_lg", "en_core_web_md", "en_core_web_sm"):
        try:
            _nlp_en = spacy.load(model)
            logger.info(f"  spaCy modèle EN chargé : {model}")
            break
        except OSError:
            continue

    try:
        _nlp_fr = spacy.load("fr_core_news_lg")
        logger.info("  spaCy modèle FR chargé : fr_core_news_lg")
    except OSError:
        pass  # Optionnel

except ImportError:
    _nlp_en = _nlp_fr = None
    logger.warning("spaCy non installé. Lancez: pip install spacy && python -m spacy download en_core_web_lg")


# ── Patterns regex ─────────────────────────────────────────────────────────────

# Chiffres clés
_KEY_METRICS_PAT = [
    (re.compile(r'(\d+\+?)\s*[Yy]ears?\s+(?:of\s+)?(?:experience|expertise)', re.I), "years_expertise"),
    (re.compile(r'(\d+\+?)\s*[Cc]ountries', re.I),                                    "countries"),
    (re.compile(r'(\d+\+?)\s*[Cc]lients?', re.I),                                     "clients_count"),
    (re.compile(r'(\d+\+?)\s*[Cc]entral\s+[Bb]anks?', re.I),                         "central_banks"),
    (re.compile(r'(\d+\+?)\s*(?:[Ee]mployees?|[Ss]taff|[Tt]eam\s+[Mm]embers?)', re.I), "employees"),
    (re.compile(r'(\d+\+?)\s*[Ll]ocations?', re.I),                                   "offices"),
    (re.compile(r'(\d+\+?)\s*[Pp]rojects?\s+[Cc]ompleted', re.I),                    "projects"),
    (re.compile(r'(\d+)%?\+?\s*[Ss]taff.*?R&D', re.I),                               "staff_rd_percent"),
]

# Année de fondation
_FOUNDED_PAT = re.compile(
    r'(?:founded|established|created|launched|incorporated|since|depuis)\s*(?:in\s+)?(\b(?:19|20)\d{2}\b)',
    re.IGNORECASE
)

# Effectif
# Effectif — exclut "30+ Staff percentage in R&D"
_EMPLOYEES_PAT = re.compile(
    r'(\d[\d,]*\+?)\s*(?:employees?|collaborators?|team\s+members?|salariés?)'
    r'(?!\s+percentage)',
    re.IGNORECASE
)

# Chiffre d'affaires
_REVENUE_PAT = re.compile(
    r"(?:revenue|turnover|chiffre\s+d['\u2019]affaires?)\s*[:\s]*"
    r'([€$£]?\s*\d[\d\s,\.]*\s*(?:M|B|K|million|billion|milliard)?[€$£]?)',
    re.IGNORECASE
)

# Témoignages : citation entre guillemets + attribution
_REVIEW_PAT = re.compile(
    r'["\u201c\u201e\u2018\u00AB](.{30,600}?)["\u201d\u2019\u00BB]'
    r'\s*(?:[-–—]\s*)?([A-Z][A-Z\s]{2,40})'
    r'(?:\s*[,\n]\s*(.{5,100}))?',
    re.DOTALL
)

# Certifications
_CERT_PAT = re.compile(
    r'\b(ISO[/\s-]?\d{5}(?::\d{4})?'
    r'|SOC\s*[12](?:\s+Type\s+[IVX1-9]+)?'
    r'|SWIFT[^\n,.]{0,40}(?:Certification|Label|Compatible)[^\n,.]{0,30}'
    r'|PCI[- ]DSS'
    r'|GDPR\s*[Cc]ompliant'
    r'|ISO\s*27\d{3}(?::\d{4})?)\b',
    re.IGNORECASE
)

# Titres de poste (pour détecter les dirigeants)
_TITLE_PAT = re.compile(
    r'\b(CEO|CTO|CFO|COO|CMO|CSO|CIO|CISO|CPO|CRO'
    r'|Chairman|President|Vice[- ]President|VP'
    r'|Managing\s+Director|Executive\s+Director|General\s+Manager'
    r'|Head\s+of\s+\w+(?:\s+\w+)?'
    r'|Director(?:\s+(?:General|of\s+\w+(?:\s+\w+)?))?'
    r'|Directeur(?:\s+Général)?|Président(?:\s+Directeur\s+Général)?|PDG|DG'
    r'|(?:Legal|Finance|Operations?|Compliance|Risk|Sales|Marketing)\s+(?:Director|Manager|Lead)?)\b',
    re.IGNORECASE
)

# Noms propres en MAJUSCULES (style Vermeg : "Tarak ACHICH", "BADREDDINE OUALI")
_UPPER_NAME_PAT = re.compile(
    r'\b([A-Z][a-z]+\s+[A-Z]{2,}(?:\s+[A-Z]{2,})?)\b'  # Prénom NOM
    r'|'
    r'\b([A-Z]{2,}(?:\s+[A-Z]{2,})+)\b'                  # NOM NOM
)

# Technologies / frameworks
_TECH_PHRASES = [
    "SaaS", "PaaS", "IaaS", "API", "REST", "microservices",
    "Kubernetes", "Docker", "DevOps", "cloud", "low-code", "no-code",
    "AI", "machine learning", "deep learning", "NLP", "AIOps",
    "blockchain", "PostgreSQL", "CDM", "SWIFT", "EMIR", "EMIR REFIT",
    "Dodd-Frank", "Basel III", "MiFID", "SOC 2", "ISO 27001",
]

# Secteurs d'activité
_SECTOR_PHRASES = [
    "Capital Markets", "Insurance", "Banking", "Asset Management",
    "Collateral Management", "Post-Trade", "FinTech", "Compliance",
    "Regulatory", "Life & Pension", "Healthcare", "Property & Casualty",
    "Market Infrastructure", "Asset Servicing", "Wealth Management",
]

# Mots-clés contexte client (pour filtrer les ORG)
_CLIENT_CTX = re.compile(
    r'(?:client|customer|reference|partner|trusted\s+by|case\s+study'
    r'|testimonial|we\s+help|we\s+serve|serves?)',
    re.IGNORECASE
)


# ── Collecte des textes ────────────────────────────────────────────────────────

def _collect_texts(company: dict) -> dict:
    """Collecte les clean_text disponibles, indexés par nom de page."""
    texts = {}
    wd = company.get("welcome_data", {})
    if isinstance(wd, dict) and wd.get("clean_text"):
        texts["welcome"] = wd["clean_text"]
    for page, data in (company.get("secondary_data") or {}).items():
        if isinstance(data, dict) and data.get("clean_text"):
            texts[page] = data["clean_text"]
    return texts


# ── Extracteurs regex ──────────────────────────────────────────────────────────

def _extract_key_metrics(texts: dict) -> dict:
    full = " ".join(texts.values())
    out = {}
    for pat, key in _KEY_METRICS_PAT:
        m = pat.search(full)
        if m:
            out[key] = m.group(1).strip().replace(",", "")
    return out


def _extract_certifications(texts: dict) -> list:
    full = " ".join(texts.values())
    seen, found = set(), []
    for m in _CERT_PAT.finditer(full):
        # Prendre uniquement le groupe capturé (pas de texte parasite autour)
        cert = re.sub(r'\s+', ' ', m.group(1).strip())
        key  = re.sub(r'\s+', '', cert).upper()
        if key not in seen:
            seen.add(key)
            found.append(cert)
    return found


def _extract_technologies(texts: dict) -> list:
    full = " ".join(texts.values())
    return [t for t in _TECH_PHRASES
            if re.search(r'\b' + re.escape(t) + r'\b', full, re.IGNORECASE)]


def _extract_sectors(texts: dict) -> list:
    full = " ".join(texts.values())
    return [s for s in _SECTOR_PHRASES
            if re.search(r'\b' + re.escape(s) + r'\b', full, re.IGNORECASE)]


def _extract_reviews(texts: dict, company_name: str = "") -> list:
    """Extrait les témoignages clients (citations + attribution)."""
    text = " ".join(texts.get(p, "") for p in ["welcome", "clients", "about"])
    reviews = []
    seen    = set()
    own     = (company_name or "").lower()

    # Mots qui indiquent que ce n'est PAS un témoignage client
    _NOT_REVIEW = re.compile(
        r'\b(certification|award|certifi|label|FTF|SWIFT\s+Certif'
        r'|honored\s+to\s+receive|proud\s+to\s+win|ISO|SOC)\b',
        re.IGNORECASE
    )

    for m in _REVIEW_PAT.finditer(text):
        quote  = re.sub(r'\s+', ' ', m.group(1).strip())
        author = m.group(2).strip()
        role   = (m.group(3) or "").strip()

        # Filtres qualité
        if len(quote) < 30:
            continue
        if author.upper() in seen:
            continue
        # Exclure si le texte parle de certif/award (faux positif)
        if _NOT_REVIEW.search(quote):
            continue
        # Exclure les discours internes (Chairman/CEO de l'entreprise elle-même)
        if own and own in role.lower():
            continue

        entry = f'"{quote}" — {author}'
        if role:
            entry += f", {role}"
        seen.add(author.upper())
        reviews.append(entry)

    return reviews[:8]


def _extract_founded_year(texts: dict) -> int | None:
    for page in ["about", "welcome"]:
        m = _FOUNDED_PAT.search(texts.get(page, ""))
        if m:
            return int(m.group(1))
    return None


def _extract_employees_count(texts: dict) -> str | None:
    full = " ".join(texts.values())
    m = _EMPLOYEES_PAT.search(full)
    return m.group(1).replace(",", "") if m else None


def _extract_revenue(texts: dict) -> str | None:
    full = " ".join(texts.values())
    m = _REVENUE_PAT.search(full)
    return re.sub(r'\s+', ' ', m.group(1).strip()) if m else None


# ── NER spaCy ─────────────────────────────────────────────────────────────────

def _run_ner(texts: dict, nlp_en, nlp_fr) -> tuple[list, list, list]:
    """
    Lance spaCy NER sur les textes.
    Retourne (persons, orgs, geo_locations).
    """
    persons, orgs, geos = [], [], []
    priority = ["leadership", "team", "about", "welcome", "clients", "contact"]

    for page in priority + [p for p in texts if p not in priority]:
        text = texts.get(page, "")
        if not text:
            continue

        # Choisir le bon modèle selon la langue détectée
        # Heuristique simple : plus de mots français → modèle FR
        fr_markers = len(re.findall(r'\b(?:nous|notre|les|des|est|son|sur|avec|pour)\b', text, re.I))
        en_markers = len(re.findall(r'\b(?:the|our|we|is|are|with|for|and|of)\b', text, re.I))
        nlp = (nlp_fr if nlp_fr and fr_markers > en_markers else nlp_en)
        if nlp is None:
            continue

        doc = nlp(text[:60_000])
        for ent in doc.ents:
            val = ent.text.strip()
            if not val or len(val) < 2:
                continue
            ctx_start = max(0, ent.start_char - 80)
            ctx_end   = min(len(text), ent.end_char + 80)
            ctx       = text[ctx_start:ctx_end].replace("\n", " ")

            if ent.label_ == "PERSON" and len(val) > 4:
                persons.append({"name": val, "context": ctx, "page": page})
            elif ent.label_ == "ORG" and len(val) > 2:
                orgs.append({"name": val, "context": ctx, "page": page})
            elif ent.label_ in ("GPE", "LOC") and len(val) > 2:
                geos.append(val)

    return persons, orgs, geos


def _extract_team_leaders_from_persons(persons: list, texts: dict) -> list | None:
    """
    Construit la liste des dirigeants.
    Priorité à la méthode regex (NOM MAJUSCULE + titre) sur leadership/about,
    puis NER spaCy en complément.
    """
    leaders = []
    seen    = set()

    # Mots non-personnes à exclure
    _NOT_PERSON = {
        "LINKEDIN", "TWITTER", "YOUTUBE", "FACEBOOK", "INSTAGRAM",
        "VERMEG", "CONFOLINE", "ONETECH", "MICROSOFT", "GOOGLE",
        "SWIFT", "ISO", "SOC", "API", "EMIR", "CSR",
    }

    # ── Méthode 1 : regex NOM MAJUSCULE + titre (fiable pour pages structurées) ─
    for page in ["leadership", "about", "team", "welcome"]:
        text = texts.get(page, "")
        if not text:
            continue
        for m in re.finditer(
            r'([A-Z][a-z]{1,20}\s+[A-Z]{2,15}(?:\s+[A-Z]{2,15})?)'   # Prénom NOM (NOM)
            r'\s+'
            r'(CEO|CTO|CFO|COO|CMO|CIO|CISO|Co-CEO'
            r'|Chairman|President|Director General|Managing Director'
            r'|Legal|Finance|Operations?|Compliance|Risk'
            r'|Europe\s*(?:&|and)?\s*UK|APAC|Americas'
            r'|Market\s+Operations?)',
            text
        ):
            name  = m.group(1).strip()
            title = m.group(2).strip()
            key   = name.upper()
            if key not in seen and key not in _NOT_PERSON and len(name) > 5:
                leaders.append({"name": name, "title": title})
                seen.add(key)

    # ── Méthode 2 : NER spaCy en complément (sur pages leadership uniquement) ──
    for p in [x for x in persons if x.get("page") in ("leadership", "team", "about")]:
        name = p["name"]
        key  = name.upper()
        # Filtrer les noms évidents non-personnes
        if key in _NOT_PERSON or len(name) < 6:
            continue
        # Exclure si contient des caractères non-nom
        if re.search(r'[&@#\d]', name):
            continue
        if key not in seen:
            tm = _TITLE_PAT.search(p["context"])
            if tm:
                leaders.append({"name": name, "title": tm.group(0).strip(" .,")})
                seen.add(key)

    return leaders if leaders else None


def _extract_locations_from_geo(geos: list, texts: dict) -> list:
    """Déduplique et filtre les localisations géographiques."""
    seen, result = set(), []
    # Priorité aux villes explicitement dans la page contact
    contact_text = texts.get("contact", "")
    for m in re.finditer(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[–-]\s*[A-Z][a-z]+\s*\(', contact_text):
        city = m.group(1).strip()
        if city.upper() not in seen:
            seen.add(city.upper())
            result.append(city)

    for geo in geos:
        if geo.upper() not in seen:
            seen.add(geo.upper())
            result.append(geo)
    return result[:25]


def _extract_orgs_mentioned(orgs: list, company_name: str) -> list:
    """Organisations tierces mentionnées (clients potentiels, partenaires...)."""
    own = (company_name or "").lower()
    _NOISE = {"linkedin", "twitter", "youtube", "facebook", "instagram",
              "wikipedia", "github", "google", "microsoft"}
    seen, result = set(), []
    for o in orgs:
        name = o["name"]
        # Filtres :
        # - longueur raisonnable (3–60 chars)
        # - pas plus de 2 "&" (sinon c'est du nav menu)
        # - pas de chiffres isolés
        # - pas le nom de l'entreprise elle-même
        # - pas des mots réseaux sociaux
        if (len(name) < 4 or len(name) > 60):
            continue
        if name.count("&") > 1:
            continue
        if re.search(r'^\d+', name.strip()):
            continue
        if own and own in name.lower():
            continue
        if name.lower() in _NOISE:
            continue
        key = name.upper()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result[:25]


# ── Fonction principale ────────────────────────────────────────────────────────

def enrich_with_nlp(company: dict) -> dict:
    """
    Phase 7 — Enrichissement NLP avec spaCy.

    - Remplit les champs null restants (team_leaders, reviews, founded_year, employees_count)
    - Ajoute de nouveaux champs : key_metrics, certifications, technologies,
      sectors, locations_geo, orgs_mentioned

    Args:
        company : dict entreprise après Phase 6

    Returns:
        company enrichi
    """
    if _nlp_en is None:
        logger.warning("  Phase 7 ignorée — spaCy non disponible")
        logger.warning("  Installez: pip install spacy && python -m spacy download en_core_web_lg")
        return company

    logger.info("  Phase 7 — Enrichissement spaCy NLP")

    texts = _collect_texts(company)
    if not texts:
        logger.warning("  Aucun texte disponible pour le NLP")
        return company

    logger.info(f"  Pages analysées : {list(texts.keys())}")

    # ── NER ────────────────────────────────────────────────────────────────────
    persons, orgs, geos = _run_ner(texts, _nlp_en, _nlp_fr)
    logger.info(f"  NER → {len(persons)} personnes | {len(orgs)} orgs | {len(geos)} lieux")

    # ── Remplir les champs null ────────────────────────────────────────────────
    filled = 0

    if company.get("team_leaders") is None:
        leaders = _extract_team_leaders_from_persons(persons, texts)
        if leaders:
            company["team_leaders"] = leaders
            logger.info(f"  [team_leaders] {len(leaders)} dirigeants → {[l['name'] for l in leaders[:3]]}")
            filled += 1

    if company.get("reviews") is None:
        reviews = _extract_reviews(texts, company_name=company.get("company_name", ""))
        if reviews:
            company["reviews"] = reviews
            logger.info(f"  [reviews] {len(reviews)} témoignages")
            filled += 1

    if company.get("founded_year") is None:
        year = _extract_founded_year(texts)
        if year:
            company["founded_year"] = year
            logger.info(f"  [founded_year] {year}")
            filled += 1

    if company.get("employees_count") is None:
        emp = _extract_employees_count(texts)
        if emp:
            company["employees_count"] = emp
            logger.info(f"  [employees_count] {emp}")
            filled += 1

    if company.get("revenue") is None:
        rev = _extract_revenue(texts)
        if rev:
            company["revenue"] = rev
            logger.info(f"  [revenue] {rev}")
            filled += 1

    logger.info(f"  {filled} champs null remplis par NLP")

    # ── Nouveaux champs enrichis ───────────────────────────────────────────────
    metrics = _extract_key_metrics(texts)
    if metrics:
        company["key_metrics"] = metrics
        logger.info(f"  [key_metrics] {metrics}")

    certs = _extract_certifications(texts)
    if certs:
        company["certifications"] = certs
        logger.info(f"  [certifications] {certs}")

    techs = _extract_technologies(texts)
    if techs:
        company["technologies"] = techs
        logger.info(f"  [technologies] {techs}")

    sectors = _extract_sectors(texts)
    if sectors:
        company["sectors"] = sectors
        logger.info(f"  [sectors] {sectors}")

    locs = _extract_locations_from_geo(geos, texts)
    if locs:
        company["locations_geo"] = locs
        logger.info(f"  [locations_geo] {locs[:5]}{'...' if len(locs) > 5 else ''}")

    orgs_mentioned = _extract_orgs_mentioned(orgs, company.get("company_name"))
    if orgs_mentioned and company.get("clients") is None:
        company["orgs_mentioned"] = orgs_mentioned
        logger.info(f"  [orgs_mentioned] {len(orgs_mentioned)} organisations")

    return company
