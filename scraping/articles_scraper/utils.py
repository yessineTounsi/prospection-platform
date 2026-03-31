import re
import json
import time
import random
from config import MIN_DELAY, MAX_DELAY


# ─────────────────────────────────────────────
#  UTILITAIRES DE BASE
# ─────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Supprime les espaces multiples et strips."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def random_delay():
    """Pause aléatoire entre MIN_DELAY et MAX_DELAY secondes."""
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def get_browser_headers() -> dict:
    """Headers HTTP imitant un navigateur Chrome réel."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
    }


def extract_meta(soup, attr_name: str, attr_value: str) -> str:
    """Extrait la valeur d'une balise <meta> depuis un objet BeautifulSoup."""
    tag = soup.find("meta", attrs={attr_name: attr_value})
    if tag and tag.get("content"):
        return clean_text(tag["content"])
    return ""


def detect_language(text: str) -> str:
    """Détecte si le texte est en français ou en anglais."""
    text = f" {(text or '').lower()} "
    french_words  = [" le ", " la ", " les ", " de ", " des ", " et ", " pour ", " avec ", " une ", " un "]
    english_words = [" the ", " and ", " for ", " with ", " of ", " in ", " on ", " a ", " an "]
    fr_score = sum(word in text for word in french_words)
    en_score = sum(word in text for word in english_words)
    return "fr" if fr_score > en_score else "en"


def flatten_for_csv(value) -> str:
    """Sérialise listes et dicts pour écriture CSV."""
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value