"""
config.py — Paramètres centralisés du pipeline Sales Intelligence
"""
from pathlib import Path

# ── Chemins ───────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
OUTPUT_MD       = BASE_DIR / "output" / "md"
OUTPUT_JSON     = BASE_DIR / "output" / "json"
OUTPUT_FINAL    = BASE_DIR / "output" / "final"
LOGS_DIR        = BASE_DIR / "logs"
PROGRESS_FILE   = BASE_DIR / "progress.json"

# ── Scraping ──────────────────────────────────────────────────
CRAWL4AI_HEADLESS           = True
CRAWL4AI_DELAY              = 6
CRAWL4AI_TIMEOUT            = 30000
CRAWL4AI_RETRY              = 1

DELAY_BETWEEN_URLS_MIN      = 2.0
DELAY_BETWEEN_URLS_MAX      = 5.0

FLARESOLVERR_URL            = "http://localhost:8191/v1"
FLARESOLVERR_TIMEOUT        = 60000

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
]

# ── Pipeline ──────────────────────────────────────────────────
STOP_ON_ERROR               = True
SAVE_PARTIAL_RESULTS        = True