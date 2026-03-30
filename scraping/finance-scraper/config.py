# finance/config.py
"""
Configuration centralisée de la couche finance.
Tous les seuils et flags sont ici — pas dans le code métier.
"""

# Seuil de confiance minimum pour accepter un match
MIN_SCORE_PAPPERS = 0.50   # score interne pappers (0–100 → normalisé 0.0–1.0)
MIN_SCORE_YAHOO   = 0.35   # _match_score yahoo (déjà 0.0–1.0)

# Si Pappers échoue sur une entreprise FR, tenter Yahoo ?
FALLBACK_YAHOO_IF_PAPPERS_FAILS = True

# Si country est None, tenter Yahoo directement ?
TRY_YAHOO_IF_NO_COUNTRY = True

# Variantes de pays considérées comme "France"
FRANCE_VARIANTS = {
    "france", "fr", "french", "française",
    "francaise", "france metropolitaine"
}