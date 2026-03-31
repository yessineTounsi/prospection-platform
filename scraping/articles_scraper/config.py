import requests
import cloudscraper

# ─────────────────────────────────────────────
#  CONFIGURATION GLOBALE
# ─────────────────────────────────────────────

API_KEY                   = "ad38b88faa7956fac8640062bd3702b4"
REQUEST_TIMEOUT           = 10   # ✅ réduit : était 25s
MIN_DELAY                 = 0.2  # ✅ réduit : était 1.0s
MAX_DELAY                 = 0.5  # ✅ réduit : était 2.0s
FILTER_NEGATIVE_THRESHOLD = 0
MAX_PAGINATION_PAGES      = 1
MAX_DISCOVERY_URLS        = 15   # ✅ réduit : était 30
ARTICLE_LIMIT             = 15
SCRAPER_THREADS           = 5    # ✅ NOUVEAU : scraping parallèle (5 threads)

MIN_ARTICLE_PATH_LENGTH   = 20

DB_NAME = "scraping_articles.db"

session = requests.Session()
cloud_session = cloudscraper.create_scraper(browser={
    "browser": "chrome",
    "platform": "windows",
    "mobile": False
})

SITEMAP_PATHS = [
    "/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
    "/sitemaps/sitemap.xml", "/news-sitemap.xml",
    "/blog-sitemap.xml", "/post-sitemap.xml", "/page-sitemap.xml",
]

SITEMAP_CONTENT_KEYWORDS = [
    "blog", "news", "article", "post", "press", "insight",
    "update", "publication", "media", "actualite", "actualité"
]

NAV_KEYWORDS = [
    "blog", "news", "newsroom", "insights", "articles", "resources",
    "press", "updates", "media", "publications", "actualités", "actualites",
    "presse", "journal", "magazine", "stories", "thoughts", "perspectives"
]

HARDCODED_PATHS = [
    "/blog", "/news", "/newsroom", "/insights", "/articles",
    "/resources", "/press", "/updates", "/media", "/publications",
    "/en/news", "/fr/news", "/en/blog", "/fr/blog",
    "/en/insights", "/fr/insights", "/en/press", "/fr/press",
    "/en/newsroom", "/fr/newsroom", "/en/resources", "/fr/resources",
    "/company/news", "/company/blog", "/about/news",
    "/actualites", "/actualités", "/presse", "/journal",
]

BAD_PATH_PATTERNS = [
    "/about", "/team", "/career", "/careers", "/job", "/jobs",
    "/service", "/legal", "/privacy", "/contact",
    "/mission", "/vision", "/strategy", "/faq",
    "/page/", "/tag/", "/tags/", "/category/", "/categories/",
    "/author/", "/authors/", "/search", "/feed",
    "/i/", "/agency", "/company", "/profile",
    "/listing", "/directory", "/find/", "/hire/",
    "/portfolio", "/reviews", "/compare",
    "/pricing", "/plans",
    "/login", "/signup", "/register",
    "/dashboard", "/account", "/settings",
    "/advertising", "/branding", "/animation", "/communication",
    "/design", "/development", "/ecommerce", "/marketing",
    "/social-media", "/video", "/ux-", "/3d-",
    "/software", "/mobile", "/app-", "/web-",
    "/international", "/artificial", "/public-relations",
    "/data-", "/content-", "/media-", "/email-",
    "/event", "/innovation",
]

NEGATIVE_KEYWORDS = [
    "basketball", "football", "soccer", "golf", "tennis", "match",
    "fantasy", "shoe", "shoes", "recipe", "food", "kitchen",
    "lyrics", "coupon", "discount", "hotel", "travel"
]