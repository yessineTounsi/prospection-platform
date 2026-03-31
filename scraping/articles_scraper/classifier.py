from config import NEGATIVE_KEYWORDS


# ─────────────────────────────────────────────
#  SCORING DE PERTINENCE
# ─────────────────────────────────────────────

def get_relevance_score(company_name: str, title: str, text: str) -> float:
    """
    Calcule un score de pertinence pour un article par rapport à l'entreprise.
    Score positif = article pertinent, négatif = hors-sujet.
    """
    company = (company_name or "").lower().strip()
    title_l = (title or "").lower()
    text_l  = (text or "").lower()
    score   = 0

    if company and company in title_l:
        score += 3

    company_count = text_l.count(company) if company else 0
    if company_count >= 1:
        score += 2
    if company_count >= 2:
        score += 1

    score -= sum(3 for kw in NEGATIVE_KEYWORDS if kw in title_l or kw in text_l)
    return score


def get_relevance_info(company_name: str, title: str, text: str, source: str = "") -> dict:
    """
    Retourne un dictionnaire de diagnostic détaillé sur la pertinence d'un article.
    """
    company = (company_name or "").lower().strip()
    title_l = (title or "").lower()
    text_l  = (text or "").lower()

    return {
        "company_in_title":       company in title_l if company else False,
        "company_count_in_text":  text_l.count(company) if company else 0,
        "negative_hits":          [kw for kw in NEGATIVE_KEYWORDS if kw in title_l or kw in text_l],
        "has_full_text":          len(text_l) > 200,
        "source":                 source,
    }


# ─────────────────────────────────────────────
#  CLASSIFICATION DU TYPE D'ARTICLE
# ─────────────────────────────────────────────

def detect_article_type(text: str) -> str:
    """
    Détecte le type d'article parmi : finance, product, partnership, funding, general.
    """
    text_l = (text or "").lower()

    if any(k in text_l for k in ["stock", "shares", "valuation", "investors", "nasdaq", "market cap"]):
        return "finance"
    if any(k in text_l for k in ["launch", "product", "feature", "tool", "platform", "service", "software", "app"]):
        return "product"
    if any(k in text_l for k in ["partnership", "collaboration", "partnered", "alliance"]):
        return "partnership"
    if any(k in text_l for k in ["funding", "raised", "investment round", "series a", "series b", "seed round"]):
        return "funding"
    return "general"


def classify_subject(text: str) -> list:
    """
    Classifie le sujet de l'article parmi les catégories métier prédéfinies.
    Retourne une liste (plusieurs catégories possibles).
    """
    text_lower = (text or "").lower()
    rules = {
        "levee_fonds":            ["funding round", "raised", "raises", "investment round", "series a", "series b", "seed round"],
        "nomination":             ["appointed", "joins as", "new ceo", "chief executive officer"],
        "nouveau_produit_service":["launches", "launched", "introduces", "new product", "new service", "unveiled"],
        "acquisition_rachat":     ["acquisition", "acquire", "acquires", "acquired", "merger", "takeover"],
        "difficulte":             ["layoffs", "bankruptcy", "losses", "shutdown", "restructuring"],
        "partenariat":            ["partnership", "partners with", "collaboration", "alliance"],
    }
    found = [cat for cat, kws in rules.items() if any(kw in text_lower for kw in kws)]
    return found if found else ["autre"]