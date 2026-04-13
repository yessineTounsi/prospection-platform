"""
navigation/link_extractor.py
============================
Extraction et pre-filtrage des liens internes.

Blacklist : uniquement le structurellement inutile.
  Retiré : careers, emploi, recrutement, jobs, investor, actionnaire
  Raison  : pages RH contiennent organigramme et dirigeants,
            pages investisseurs contiennent structure et gouvernance.
            Le scorer sémantique les classe en team / about.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse


_ASSET_EXT = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.avif',
    '.pdf', '.ico', '.mp4', '.mp3', '.zip', '.css', '.js',
    '.woff', '.woff2',
}

_EXCLUDED_DOMAINS = {
    'facebook.com', 'twitter.com', 'instagram.com', 'youtube.com',
    'linkedin.com', 'google.com', 'apple.com', 'play.google.com',
    'maps.google', 'goo.gl', 'bit.ly', 'tiktok.com', 'pinterest.com',
    'whatsapp.com', 'telegram.org', 'adroll.com',
}

# Tokens exacts — split sur espaces et '/' uniquement (pas les tirets)
# 'support-it' ne matche PAS 'support', 'rejoindre-equipe' ne matche PAS 'join'
_BLACKLIST_EXACT = {
    # Legal
    'privacy', 'cookie', 'cookies', 'legal', 'mentions', 'terms',
    'gdpr', 'rgpd', 'cgu', 'cgv', 'disclaimer', 'impressum',
    'confidentialite', 'politique',
    # Navigation technique
    'sitemap', 'login', 'signin', 'register',
    'cart', 'panier', 'checkout',
    'dashboard', 'my-account', 'mon-compte',
    # Support / FAQ — peu de valeur prospection
    'sav', 'helpdesk', 'faq',
    # RH et investisseurs EXCLUS volontairement :
    # → classés en team / about par le scorer
}

_BLACKLIST_SUBSTRING = {
    'accueil',  # welcome page déjà scrapée
}

_LANG_PREFIX = re.compile(
    r'^https?://[^/]+/(fr-fr|en-us|en-gb|de-de|es-es|it-it|nl-nl|pt-br|zh-cn|ja-jp)(/|$)',
    re.IGNORECASE
)


def _is_asset(url: str) -> bool:
    return any(urlparse(url).path.lower().endswith(e) for e in _ASSET_EXT)


def _is_external(url: str) -> bool:
    return any(d in url.lower() for d in _EXCLUDED_DOMAINS)


def _is_internal(url: str, base_url: str) -> bool:
    if not base_url:
        return True
    try:
        base_domain = urlparse(base_url).netloc.replace('www.', '')
        link_domain = urlparse(url).netloc.replace('www.', '')
        return base_domain in link_domain
    except Exception:
        return False


def _is_blacklisted(text: str, slug: str) -> bool:
    combined = (text + ' ' + slug).lower()
    tokens   = set(re.split(r'[\s/]+', combined))
    if tokens & _BLACKLIST_EXACT:
        return True
    return any(b in combined for b in _BLACKLIST_SUBSTRING)


def _is_lang_only(url: str) -> bool:
    m = _LANG_PREFIX.match(url)
    if m:
        parts = url.split('/', 4)
        return len(parts) <= 4 or not parts[4]
    return False


def _normalize_url(url: str) -> str:
    url = re.sub(r'#.*$', '', url)
    url = re.sub(r'([^:])//+', r'\1/', url)
    return url.rstrip('/')


def _url_to_slug(url: str) -> str:
    try:
        path = urlparse(url).path
        path = re.sub(r'\.[a-z]{2,4}$', '', path)
        slug = re.sub(r'[-_/]', ' ', path)
        slug = re.sub(r'\b\d+\b', '', slug)
        return re.sub(r'\s+', ' ', slug).strip().lower()
    except Exception:
        return ''


def _extract_context(md: str, start: int, end: int, window: int = 80) -> str:
    raw = md[max(0, start - window):min(len(md), end + window)]
    raw = re.sub(r'\[([^\]]*)\]\([^\)]+\)', r'\1', raw)
    raw = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', raw)
    raw = re.sub(r'#{1,4}\s*', '', raw)
    raw = re.sub(r'[*_`]', '', raw)
    return re.sub(r'\s+', ' ', raw).strip()


@dataclass
class ExtractedLink:
    url:         str
    text:        str
    url_slug:    str
    context:     str
    source_page: str  = 'welcome'
    is_internal: bool = True

    def scoring_text(self, context_weight: float = 0.3) -> str:
        """
        text <= 2 chars (icône, flèche) → slug × 3, pas de doublement de bruit.
        Sinon : text × 2 + slug (pondération standard).
        """
        text = self.text.strip()
        slug = self.url_slug.strip()

        if len(text) <= 2:
            parts = [slug, slug, slug]
        else:
            parts = [text, text, slug]

        if self.context and context_weight > 0:
            parts.append(self.context)

        return ' '.join(p for p in parts if p).strip()


def extract_links(
    markdown:      str,
    base_url:      str  = None,
    source_page:   str  = 'welcome',
    internal_only: bool = True,
) -> list:
    links   = []
    seen    = set()
    pattern = re.compile(r'\[([^\]]*)\]\((https?://[^\)\s]+)\)')

    for match in pattern.finditer(markdown):
        text = match.group(1).strip()
        url  = match.group(2).strip().rstrip(') ')

        if not url or not url.startswith('http'):
            continue
        if _is_asset(url) or _is_external(url):
            continue

        url = _normalize_url(url)
        if not url or url in seen:
            continue
        if _is_lang_only(url):
            continue

        is_int = _is_internal(url, base_url)
        if internal_only and not is_int:
            continue

        slug = _url_to_slug(url)
        ctx  = _extract_context(markdown, match.start(), match.end())

        if not text and not slug:
            continue
        if _is_blacklisted(text, slug):
            continue

        seen.add(url)
        links.append(ExtractedLink(
            url         = url,
            text        = text,
            url_slug    = slug,
            context     = ctx,
            source_page = source_page,
            is_internal = is_int,
        ))

    return links


def extract_links_from_bundle(
    pages:         dict,
    base_url:      str  = None,
    internal_only: bool = True,
) -> list:
    """
    Extrait les liens depuis un bundle de pages déjà scrapées.

    Args:
        pages    : dict {source_page: markdown_content}
                   ex: {'welcome': '...', 'about': '...'}
        base_url : URL de base du site pour filtrer les liens internes

    Returns:
        Liste dédupliquée de ExtractedLink toutes pages confondues
    """
    all_links = []
    seen_urls = set()

    for source_page, markdown in pages.items():
        if not markdown:
            continue
        for link in extract_links(
            markdown      = markdown,
            base_url      = base_url,
            source_page   = source_page,
            internal_only = internal_only,
        ):
            if link.url not in seen_urls:
                seen_urls.add(link.url)
                all_links.append(link)

    return all_links