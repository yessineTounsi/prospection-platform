import re

IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp', '.avif', '.pdf', '.ico']

CDN_DOMAINS = [
    'digitalassets.', 'assets.', 'images.', 'img.', 'static.',
    'cdn.', 'media.', 'cloudfront.', 'akamai.', 'cookielaw.',
    'scene7.', 'ctfassets.', 'wp-content', 'uploads.',
]

EXCLUDED_WEBSITE_DOMAINS = [
    'facebook.com', 'twitter.com', 'instagram.com', 'youtube.com',
    'linkedin.com', 'google.com', 'apple.com', 'play.google.com',
    'maps.google', 'goo.gl', 'bit.ly', 'tiktok.com', 'pinterest.com',
]

# Sous-domaines a exclure du website_url (correction #1)
EXCLUDED_SUBDOMAINS = [
    'newsroom.', 'legal.', 'app.', 'blog.', 'community.',
    'help.', 'support.', 'status.', 'developer.', 'developers.',
    'adroll.', 'ads.', 'tracking.', 'analytics.',
]


def _is_asset_url(url):
    url_lower = url.lower()
    if any(url_lower.endswith(ext) for ext in IMAGE_EXTENSIONS):
        return True
    try:
        domain = url_lower.split('/')[2]
        if any(cdn in domain for cdn in CDN_DOMAINS):
            return True
    except IndexError:
        pass
    return False


def _is_social_url(url):
    url_lower = url.lower()
    return any(d in url_lower for d in EXCLUDED_WEBSITE_DOMAINS)


def _is_subdomain_url(url):
    """Correction #1 — rejette les sous-domaines non pertinents."""
    url_lower = url.lower()
    return any(url_lower.startswith('https://' + s) or
               url_lower.startswith('http://' + s)
               for s in EXCLUDED_SUBDOMAINS)


def extract_email(md):
    match = re.search(r'\b([a-zA-Z0-9][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b', md)
    if match:
        email = match.group(0)
        if any(email.endswith(ext) for ext in ['.png', '.jpg', '.svg', '.gif', '.webp']):
            return None
        return email
    return None


def extract_phone(md):
    match = re.search(r'(\+\d[\d\s\-\.]{7,}\d)', md)
    return match.group(0).strip() if match else None


def extract_linkedin(md):
    match = re.search(r'https?://(?:www\.)?linkedin\.com/company/[^\s\)"]+', md)
    return match.group(0).rstrip("/") if match else None


def extract_website_url(md, filename):
    """
    Correction #1 — priorite au domaine de l'URL d'entree (filename).
    Rejette les sous-domaines non pertinents (newsroom., legal., app., adroll...).
    """
    domain_hint = (
        filename
        .replace(".md", "")
        .replace("www_", "")
        .split("_")[0]
    )

    all_links = re.findall(r'\]\((https?://[^\)]+)\)', md)

    clean_links = [
        url for url in all_links
        if not _is_asset_url(url)
        and not _is_social_url(url)
        and not _is_subdomain_url(url)
    ]

    # Priorite 1 : URL qui contient le domain_hint
    for url in clean_links:
        if domain_hint.lower() in url.lower():
            return "/".join(url.split("/")[:3])

    bare_links = re.findall(r'https?://[a-zA-Z0-9.\-]+\.[a-z]{2,}(?:/[^\s\)\"\'<>]*)?', md)
    clean_bare = [
        url for url in bare_links
        if not _is_asset_url(url)
        and not _is_social_url(url)
        and not _is_subdomain_url(url)
    ]

    for url in clean_bare:
        if domain_hint.lower() in url.lower():
            return "/".join(url.split("/")[:3])

    if clean_links:
        return "/".join(clean_links[0].split("/")[:3])

    return None


def extract_logo(md):
    EXCLUDED_DOMAINS = [
        'cookielaw.org', 'onetrust.com', 'cdn.cookielaw', 'cdn.onetrust', 'static/powered_by',
    ]
    EXCLUDED_KEYWORDS = [
        'thumbnail', 'campaign', 'hero', 'banner', 'promo',
        'patient', 'people', 'employee', 'story', 'background',
        'movie', 'video', 'surf', 'sport', 'lifestyle', 'powered_by', 'static/ot_',
    ]

    matches = re.finditer(
        r'!\[[^\]]*\]\((https?://[^\)]+(?:logo|brand)[^\)]*)\)',
        md, re.IGNORECASE
    )

    for match in matches:
        url = match.group(1)
        url_lower = url.lower()
        if any(ex in url_lower for ex in EXCLUDED_DOMAINS):
            continue
        if any(kw in url_lower for kw in EXCLUDED_KEYWORDS):
            continue
        return url

    return None


def extract_address(md):
    STREET_KEYWORDS = r'\b(?:rue|avenue|boulevard|street|road|blvd|ave|st|drive|dr|lane|ln|place|pl|way|wy)\b'

    def _clean_address(raw):
        noise_cutoff = re.search(
            r'(?:\s*[,\-]\s*(?:phone|tel|fax|email|www|http|\*|•|\|)|\s{2,}\*|\s{2,}•)',
            raw, re.IGNORECASE
        )
        if noise_cutoff:
            raw = raw[:noise_cutoff.start()]
        raw = re.sub(r'\s+,', ',', raw)
        return raw.strip().rstrip(",- ")

    full = re.search(
        rf'(\d{{1,4}}[,\s]+{STREET_KEYWORDS}[^\n]{{5,80}}(?:\n[^\n]{{5,60}})?)',
        md, re.IGNORECASE
    )
    if full:
        raw = full.group(1).replace("\n", ", ")
        return _clean_address(raw)

    match = re.search(
        rf'\d{{1,4}}[,\s]+{STREET_KEYWORDS}[^\n]{{5,80}}',
        md, re.IGNORECASE
    )
    if match:
        return _clean_address(match.group(0))

    return None


def extract_country(md):
    if re.search(r'https?://[^\s]*\.tn[/\s"\)]', md):
        return "Tunisia"

    if re.search(r'(?:adresse|address|headquarter|siege|siege|located)[^\n]{0,100}(?:Tunis\b|Tunisia)', md, re.IGNORECASE):
        return "Tunisia"
    if re.search(r'\d{4}\s+Tunis', md, re.IGNORECASE):
        return "Tunisia"

    CONTEXT_KEYWORDS = r'(?:siege|headquarter|head office|based in|located|adresse|address|registered)'
    countries_map = {
        "France": "France",
        "Tunisia": "Tunisia",
        "Tunisie": "Tunisia",
        "Morocco": "Morocco",
        "Maroc": "Morocco",
        "USA": "USA",
        "United States": "USA",
        "United Kingdom": "United Kingdom",
        "Germany": "Germany",
        "Spain": "Spain",
        "Italy": "Italy",
        "Belgium": "Belgium",
        "Switzerland": "Switzerland",
        "Canada": "Canada",
        "Algeria": "Algeria",
        "Algerie": "Algeria",
        "Senegal": "Senegal",
        "Netherlands": "Netherlands",
        "Sweden": "Sweden",
        "Japan": "Japan",
        "China": "China",
        "India": "India",
        "Brazil": "Brazil",
        "Australia": "Australia",
        "Singapore": "Singapore",
        "South Korea": "South Korea",
    }

    for country_label, country_normalized in countries_map.items():
        pattern = rf'{CONTEXT_KEYWORDS}[^\n]{{0,80}}{re.escape(country_label)}'
        if re.search(pattern, md, re.IGNORECASE):
            return country_normalized

    for country_label, country_normalized in countries_map.items():
        if country_label.lower() in md.lower():
            return country_normalized

    return None


def extract_internal_urls(md, base_url):
    """Garde pour compatibilite — remplace par navigation/link_scorer dans le pipeline."""
    TARGET_PATTERNS = [
        "about", "a-propos", "company", "entreprise",
        "team", "equipe", "leadership", "management",
        "contact", "clients", "customers", "references",
        "services", "solutions", "products",
        "investors", "investisseurs", "finance",
        "press", "presse", "news",
    ]
    IMAGE_EXT = {'.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif'}

    found = {}
    all_links = re.findall(r'\[([^\]]*)\]\((https?://[^\)]+)\)', md)

    for label, url in all_links:
        url = re.split(r'\s+["\']', url)[0].strip()
        url = url.rstrip("\" ")

        if any(url.lower().endswith(ext) for ext in IMAGE_EXT):
            continue
        if _is_social_url(url):
            continue

        if base_url:
            base_domain = base_url.split("/")[2] if len(base_url.split("/")) > 2 else ""
            if base_domain and base_domain not in url:
                continue

        for pattern in TARGET_PATTERNS:
            if pattern in url.lower() and pattern not in found:
                found[pattern] = url
                break

    return found