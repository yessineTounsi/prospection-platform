"""
navigation/link_scorer.py
=========================
Scoring sémantique des liens internes.

Corrections v2 :
  bug #1 — argmax forcé : ajout marge d ambiguïté (AMBIGUITY_MARGIN)
           si best - second < 0.04 → pénalité 15% → tombe sous threshold
  bug #2 — moyenne globale : remplacé par top-3 anchors moyennés
           _score_vs_category() au lieu de _cosine() sur vecteur moyen
  bug #3 — scoring_text() corrigé dans link_extractor.py (text vide)

Interface publique inchangée :
  LinkScorer().score_links(links, top_k, max_per_cat) → list[ScoredLink]
  scored_links_to_dict(results)      → {cat: url}
  scored_links_to_rich_dict(results) → dict enrichi
"""

import logging
import numpy as np
from dataclasses import dataclass

from navigation.categories     import CATEGORIES, SCORER_CONFIG, CATEGORIES_BY_NAME
from navigation.link_extractor import ExtractedLink

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Chargement modele : " + SCORER_CONFIG["model_name"])
        _model = SentenceTransformer(SCORER_CONFIG["model_name"])
        logger.info("Modele pret.")
    return _model


def _build_category_embeddings(model) -> dict:
    """
    Stocke tous les embeddings d anchors individuels par catégorie.
    Le scoring utilise top-k anchors au lieu d une moyenne globale.
    """
    embeddings = {}
    for cat in CATEGORIES:
        embs = model.encode(cat.anchors, show_progress_bar=False)
        embeddings[cat.name] = embs  # shape (N_anchors, dim)
    return embeddings


def _score_vs_category(link_emb: np.ndarray, cat_embs: np.ndarray) -> float:
    """
    Score = moyenne des top-3 cosinus parmi tous les anchors.
    Capture les anchors spécialisés sans noyer leur signal dans la moyenne.
    """
    norms = np.linalg.norm(cat_embs, axis=1) * np.linalg.norm(link_emb) + 1e-9
    scores = np.dot(cat_embs, link_emb) / norms
    top_k = min(SCORER_CONFIG.get("top_k_anchors", 3), len(scores))
    return float(np.sort(scores)[-top_k:].mean())


@dataclass
class ScoredLink:
    link:       ExtractedLink
    category:   str
    score:      float
    all_scores: dict


class LinkScorer:

    def __init__(self):
        self.model               = _get_model()
        self.category_embeddings = _build_category_embeddings(self.model)

    def score_links(
        self,
        links:          list,
        top_k:          int   = None,
        max_per_cat:    int   = None,
        context_weight: float = None,
    ) -> list:
        if not links:
            return []

        from config import SCORER_TOP_K, SCORER_MAX_PER_CAT
        top_k          = top_k       or SCORER_TOP_K
        max_per_cat    = max_per_cat or SCORER_MAX_PER_CAT
        context_weight = context_weight or SCORER_CONFIG["context_weight"]

        scoring_texts   = [l.scoring_text(context_weight) for l in links]
        link_embeddings = self.model.encode(
            scoring_texts, show_progress_bar=False, batch_size=32
        )

        margin = SCORER_CONFIG.get("ambiguity_margin", 0.04)

        scored = []
        for i, link in enumerate(links):
            all_scores = {
                cat.name: round(
                    _score_vs_category(link_embeddings[i], self.category_embeddings[cat.name]), 4
                )
                for cat in CATEGORIES
            }

            # Tri décroissant pour extraire best + second
            sorted_cats = sorted(all_scores, key=all_scores.__getitem__, reverse=True)
            best_cat    = sorted_cats[0]
            best_score  = all_scores[best_cat]
            second      = all_scores[sorted_cats[1]] if len(sorted_cats) > 1 else 0.0

            # Pénalité si ambiguïté : best et second trop proches
            if best_score - second < margin:
                best_score = round(best_score * 0.85, 4)

            scored.append(ScoredLink(
                link=link, category=best_cat,
                score=best_score, all_scores=all_scores
            ))

        # Filtrer par threshold
        scored = [
            s for s in scored
            if s.score >= CATEGORIES_BY_NAME[s.category].threshold
        ]

        # Trier : priorité catégorie puis score décroissant
        scored.sort(key=lambda s: (CATEGORIES_BY_NAME[s.category].priority, -s.score))

        # max_per_cat par catégorie
        results, cat_counts = [], {}
        for s in scored:
            count = cat_counts.get(s.category, 0)
            if count < max_per_cat:
                results.append(s)
                cat_counts[s.category] = count + 1

        return results[:top_k]


def scored_links_to_dict(results: list) -> dict:
    return {r.category: r.link.url for r in results}


def scored_links_to_rich_dict(results: list) -> dict:
    return {
        r.category: {
            "url":         r.link.url,
            "link_text":   r.link.text,
            "score":       round(r.score, 4),
            "source_page": r.link.source_page,
        }
        for r in results
    }


# Singleton scorer — évite de recharger le modèle à chaque appel
_scorer = None

def score_links(
    links:          list,
    top_k:          int   = None,
    max_per_cat:    int   = None,
    context_weight: float = None,
) -> list:
    """
    Fonction standalone — interface directe sans instancier LinkScorer.
    Utilise un singleton interne pour ne charger le modèle qu'une seule fois.
    """
    global _scorer
    if _scorer is None:
        _scorer = LinkScorer()
    return _scorer.score_links(
        links          = links,
        top_k          = top_k,
        max_per_cat    = max_per_cat,
        context_weight = context_weight,
    )