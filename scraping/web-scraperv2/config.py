"""
config.py — Parametres centralises du pipeline Sales Intelligence
=================================================================
Tous les parametres sont modifiables ici sans toucher au code.
"""
from pathlib import Path

# ── Chemins ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
OUTPUT_MD     = BASE_DIR / "output" / "md"
OUTPUT_JSON   = BASE_DIR / "output" / "json"
OUTPUT_FINAL  = BASE_DIR / "output" / "final"
LOGS_DIR      = BASE_DIR / "logs"
PROGRESS_FILE = BASE_DIR / "progress.json"

# ── Scraping — Crawl4AI ────────────────────────────────────────────────────────
CRAWL4AI_HEADLESS  = True
CRAWL4AI_DELAY     = 6
CRAWL4AI_TIMEOUT   = 45000

# ── Scraping — Pauses anti-ban ─────────────────────────────────────────────────
DELAY_BETWEEN_URLS_MIN = 2.0
DELAY_BETWEEN_URLS_MAX = 5.0

# ── Scraping — FlareSolverr ────────────────────────────────────────────────────
FLARESOLVERR_URL     = "http://localhost:8191/v1"
FLARESOLVERR_TIMEOUT = 60000

# ── Scraping — User Agents ─────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
]

# ── Navigation — Scorer sémantique ────────────────────────────────────────────
# 9 = 7 catégories avec marge pour max_per_cat=2 sur about/team
SCORER_TOP_K       = 9
# 2 = garde le 2ème candidat par catégorie (about, team surtout)
SCORER_MAX_PER_CAT = 2

# ── Navigation — Ollama (LLM local) ───────────────────────────────────────────
OLLAMA_URL     = "http://localhost:11434"
OLLAMA_MODEL   = "mistral"          # alternatives : llama3.2, qwen2.5:7b, gemma2
OLLAMA_TIMEOUT = 120                # secondes — augmenter si GPU lent

# ── Pipeline — Comportement ────────────────────────────────────────────────────
STOP_ON_ERROR        = False
SAVE_PARTIAL_RESULTS = True