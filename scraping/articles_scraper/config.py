import requests
import cloudscraper

# ─────────────────────────────────────────────
#  CONFIGURATION GLOBALE
# ─────────────────────────────────────────────

API_KEY                   = "c3c4570d530d2b13904f261cc261e134"
REQUEST_TIMEOUT           = 15
MIN_DELAY                 = 0.1
MAX_DELAY                 = 0.3
FILTER_NEGATIVE_THRESHOLD = 0
MAX_PAGINATION_PAGES      = 3
MAX_DISCOVERY_URLS        = 25
ARTICLE_LIMIT             = 15
SCRAPER_THREADS           = 10

MIN_ARTICLE_PATH_LENGTH   = 20

DB_NAME = "scraping_articles.db"

session = requests.Session()
cloud_session = cloudscraper.create_scraper(browser={
    "browser": "chrome",
    "platform": "windows",
    "mobile": False
})

# ─────────────────────────────────────────────
#  SITEMAP
# ─────────────────────────────────────────────

SITEMAP_PATHS = [
    "/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
    "/sitemaps/sitemap.xml", "/news-sitemap.xml",
    "/blog-sitemap.xml", "/post-sitemap.xml", "/page-sitemap.xml",
]

SITEMAP_CONTENT_KEYWORDS = [
    "blog", "news", "article", "post", "press", "insight",
    "update", "publication", "media", "story", "stories",
    "actualite", "actualité", "actualites", "actualités",
    "presse", "journal", "magazine", "communique", "communiqué",
    "akhbar", "jadid", "maqal",
]

# ─────────────────────────────────────────────
#  NAVIGATION KEYWORDS
# ─────────────────────────────────────────────

NAV_KEYWORDS = [
    # Anglais
    "blog", "news", "newsroom", "insights", "articles",
    "resources", "press", "updates", "media", "publications",
    "stories", "thoughts", "perspectives", "announcements",
    "events", "editorial", "digest", "briefing", "bulletin",
    "report", "reports", "whitepapers", "case-studies",
    "learn", "learning", "knowledge", "hub",
    # Français
    "actualité", "actualités", "actualite", "actualites",
    "nos actualités", "notre actualité",
    "presse", "communiqué", "communique",
    "journal", "magazine", "revue",
    "publication", "publications",
    "événement", "evenement", "événements", "evenements",
    "annonce", "annonces", "dossier", "dossiers",
    "tribune", "tribunes", "veille",
    "nos nouvelles", "nouvelles", "la une",
    # Espagnol
    "noticias", "novedades", "prensa",
    "articulos", "artículos", "publicaciones",
    # Portugais
    "notícias", "imprensa",
    # Arabe
    "أخبار", "مدونة", "مقالات", "الأخبار",
    "akhbar", "maqalat", "jadeed",
]

# ─────────────────────────────────────────────
#  PATHS HARDCODÉS
# ─────────────────────────────────────────────

HARDCODED_PATHS = [
    "/blog", "/news", "/newsroom", "/insights", "/articles",
    "/resources", "/press", "/updates", "/media", "/publications",
    "/stories", "/announcements", "/events", "/editorial",
    "/press-releases", "/press-room", "/knowledge",
    "/case-studies", "/whitepapers", "/reports",
    "/en/news", "/en/blog", "/en/insights",
    "/en/press", "/en/newsroom", "/en/resources",
    "/en/articles", "/en/updates", "/en/media",
    "/en/publications", "/en/stories",
    "/actualites", "/actualités",
    "/actualite", "/actualité",
    "/nos-actualites", "/nos-actualités",
    "/notre-actualite", "/notre-actualité",
    "/espace-presse", "/presse",
    "/communiques", "/communiqués",
    "/communique-de-presse",
    "/nos-articles", "/nos-publications",
    "/journal", "/magazine", "/revue",
    "/evenements", "/événements",
    "/annonces", "/nouvelles", "/nos-nouvelles",
    "/dossiers", "/veille",
    "/fr/news", "/fr/blog", "/fr/actualites",
    "/fr/insights", "/fr/press", "/fr/newsroom",
    "/fr/resources", "/fr/articles",
    "/fr/publications", "/fr/evenements",
    "/company/news", "/company/blog", "/company/press",
    "/company/updates", "/company/announcements",
    "/about/news", "/about/press",
    "/corporate/news", "/corporate/press",
    "/noticias", "/prensa", "/articulos", "/novedades",
    "/notícias", "/imprensa",
]

# ─────────────────────────────────────────────
#  PATTERNS D'EXCLUSION D'URLs
# ─────────────────────────────────────────────

BAD_PATH_PATTERNS = [
    # Médias / fichiers
    "/wp-content/", "/uploads/", "/wp-includes/",
    "/static/", "/assets/", "/images/", "/img/",
    "/fonts/", "/css/", "/js/",
    # Pages institutionnelles
    "/about", "/team", "/career", "/careers", "/job", "/jobs",
    "/legal", "/privacy", "/contact",
    "/mission", "/vision", "/strategy", "/faq",
    "/terms", "/conditions", "/cookies",
    "/who-we-are", "/our-team", "/our-story",
    "/qui-sommes", "/a-propos", "/notre-equipe",
    # Taxonomie CMS
    "/page/", "/tag/", "/tags/", "/category/", "/categories/",
    "/cat/", "/author/", "/authors/", "/search", "/feed",
    # Marketplace / catalogue
    "/i/", "/agency", "/profile",
    "/listing", "/directory", "/find/", "/hire/",
    "/portfolio", "/reviews", "/compare",
    "/pricing", "/plans",
    # Auth
    "/login", "/signin", "/signup", "/register",
    "/dashboard", "/account", "/settings",
    # Solutions / services / produits
    "/solutions", "/solution-",
    "/services/", "/nos-services", "/service-",
    "/offres", "/offre-",
    "/secteurs", "/secteur-",
    "/produits", "/produit-",
    "/platforms", "/platform-",
    # Carrières
    "/carrieres", "/carrieres-it", "/careers",
    "/offre-d-emploi", "/offre-de-stage",
    "/emploi", "/recrutement",
    # Marketplace (sortlist...)
    "/advertising", "/branding", "/animation", "/communication",
    "/design", "/development", "/ecommerce", "/marketing",
    "/social-media", "/video", "/ux-", "/3d-",
    "/software", "/mobile", "/app-", "/web-",
    "/international", "/artificial", "/public-relations",
    "/data-", "/content-", "/media-", "/email-",
    "/event", "/innovation",
    # Pages IT spécifiques
    "/identifiant-unique", "/pointage-virtuel",
    "/tele-prestation", "/motivation-de-force",
    "/solution-bpm", "/solution-de-configuration",
    "/solution-pour-structuration",
    "/dossier-medical", "/surveillance-des",
    "/solutions-de-telemedecine", "/gestion-des-conges",
    "/public-solutions", "/secteur-sante", "/secteur-telecom",
    "/expertise-telecom", "/service-d-etudes",
    "/services-d-ingenierie",
]

# Extensions à exclure
BAD_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp4", ".mp3", ".zip", ".rar",
}

# ─────────────────────────────────────────────
#  MOTS-CLÉS NÉGATIFS POUR LE SCORING
# ─────────────────────────────────────────────

NEGATIVE_KEYWORDS = [
    "basketball", "football", "soccer", "golf", "tennis", "match",
    "fantasy", "shoe", "shoes", "recipe", "food", "kitchen",
    "lyrics", "coupon", "discount", "hotel", "travel"
]