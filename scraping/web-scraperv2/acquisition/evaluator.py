import re

BLOCKED_SIGNATURES = [
    "checkingyourbrowser", "attentionrequired", "cloudflare",
    "captcha", "securitycheck", "verifyingthesecurity", "rayid"
]
JS_BLOCKED = [
    "enable javascript", "javascript is required",
    "you need to enable javascript", "please enable javascript",
]

# Ces termes indiquent une vraie page legale SEULEMENT si ils dominent le contenu
# Une page /services peut avoir "privacy policy" dans son footer -> ne pas rejeter
WRONG_PAGE_TITLES = [
    "privacy policy", "cookie policy", "personal data protection",
    "terms of service", "terms and conditions", "legal notice",
]

NAV_INDICATORS = [
    "go to **", "skip to main content", "change location",
    "main navigation", "secondary menu", "header persistent",
]


def is_content_valid(markdown: str) -> bool:
    """Validation basique — utilisee par scrapper 1."""
    if not markdown:
        return False
    text = re.sub(r"\s+", "", markdown)
    if len(text) < 500:
        return False
    for s in BLOCKED_SIGNATURES:
        if s in text.lower():
            return False
    return True


def _is_legal_page(markdown: str) -> bool:
    """
    Detecte une vraie page legale (CGU, politique de confidentialite).
    Une page est legale si :
    - Le titre principal (H1/H2) contient un terme legal
    - OU plus de 40% des lignes parlent de legal/RGPD
    Evite de rejeter les pages /services qui ont juste un footer legal.
    """
    text_lower = markdown.lower()

    # Verifier le titre principal (premiers 500 chars)
    header = text_lower[:500]
    for sig in WRONG_PAGE_TITLES:
        if sig in header:
            return True

    # Verifier la densite de termes legaux dans tout le contenu
    legal_terms = [
        "privacy policy", "cookie policy", "personal data",
        "data protection", "terms of service", "terms and conditions",
        "legal notice", "gdpr", "rgpd", "politique de confidentialite",
        "mentions legales", "conditions generales",
    ]
    total_chars = max(len(text_lower), 1)
    legal_hits  = sum(text_lower.count(t) for t in legal_terms)

    # Plus de 5 occurrences pour 1000 chars = page legale
    density = legal_hits / (total_chars / 1000)
    return density > 5


def evaluate_and_prepare(markdown: str) -> dict:
    """Evaluation avancee — utilisee par scrapper 2."""
    if not markdown:
        return {"action": "skip", "status": "too_short", "content": None, "confidence": 1.0}

    text_lower  = markdown.lower()
    text_clean  = re.sub(r"\s+", "", text_lower)
    lines       = [l.strip() for l in markdown.split('\n') if l.strip()]
    total_lines = len(lines)

    if len(text_clean) < 500:
        return {"action": "skip", "status": "too_short", "content": None, "confidence": 1.0}

    for sig in BLOCKED_SIGNATURES:
        if sig in text_clean:
            return {"action": "flaresolverr", "status": "bot_blocked", "content": None, "confidence": 0.95}

    for sig in JS_BLOCKED:
        if sig in text_lower:
            return {"action": "flaresolverr", "status": "js_blocked", "content": None, "confidence": 0.9}

    go_to_count = len(re.findall(r'go to \*\*', text_lower))
    nav_hits    = sum(1 for sig in NAV_INDICATORS if sig in text_lower)
    if go_to_count > 20 or (nav_hits >= 2 and total_lines > 150):
        real_content = _extract_after_nav(markdown)
        return {"action": "process", "status": "nav_dump", "content": real_content, "confidence": 0.85}

    # Correction : detection intelligente des pages legales
    if _is_legal_page(markdown):
        return {"action": "skip", "status": "wrong_page", "content": None, "confidence": 0.85}

    return {"action": "process", "status": "valid", "content": markdown, "confidence": 0.9}


def _extract_after_nav(markdown: str) -> str:
    lines = markdown.split('\n')
    last_nav_idx = 0
    for i, line in enumerate(lines):
        if 'go to **' in line.lower() or 'header persistent' in line.lower():
            last_nav_idx = i
    real_content = '\n'.join(lines[last_nav_idx + 1:])
    return real_content.strip() if len(real_content.strip()) >= 200 else markdown