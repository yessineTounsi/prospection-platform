# Web Scraper — Sales Intelligence

Pipeline de collecte et structuration de données web pour la prospection B2B.

---

## Architecture

```
web-scraperv2/
├── Pipeline.py              ← Point d'entrée unique
├── config.py                ← Tous les paramètres admin
│
├── acquisition/             ← Collecte des données web
│   ├── scraper1.py          ← Welcome page (Crawl4AI + FlareSolverr)
│   ├── scraper2.py          ← Pages internes sélectionnées
│   ├── crawler.py           ← Client Crawl4AI (headless Chromium)
│   ├── flaresolverr.py      ← Fallback anti-bot (FlareSolverr)
│   ├── evaluator.py         ← Validation qualité du contenu scrappé
│   ├── dns_checker.py       ← Vérification existence domaine
│   └── html_to_md.py        ← Conversion HTML → Markdown
│
├── navigation/              ← Sélection intelligente des pages
│   ├── categories.py        ← Catégories B2B + anchors FR/EN
│   ├── link_extractor.py    ← Extraction + pré-filtrage des liens
│   └── link_scorer.py       ← Scoring sémantique (sentence-transformers)
│
├── extraction/              ← Structuration des données
│   ├── md_to_json.py        ← Extraction regex (email, phone, linkedin...)
│   ├── extractors.py        ← Fonctions regex individuelles
│   ├── clean_secondary.py   ← Nettoyage pages internes
│   └── clean_internals.py   ← Nettoyage markdown + paragraphes
│
├── tests/                   ← Scripts de test standalone
│   ├── test_navigation.py   ← Test du scorer sur un .md
│   ├── test_extract_links.py
│   └── scrape_welcome_pages.py
│
└── output/
    ├── md/                  ← Markdowns bruts des welcome pages
    ├── json/                ← JSONs intermédiaires (v1, v2, v3)
    └── final/               ← Dataset final sales_intelligence_*.json
```

---

## Pipeline — 5 phases

```
URL d'entrée
     │
PHASE 1 — Scraper1
  Crawl4AI (headless) → markdown brut
  Fallback FlareSolverr si bot-protection détectée
     │
PHASE 2 — Extraction regex
  email, téléphone, LinkedIn, logo, adresse, pays
  welcome_data : clean_text + paragraphes structurés
     │
PHASE 3 — Link Scorer
  Extraction de tous les liens internes
  Pré-filtre : supprime legal, RH, assets, langue...
  Scoring sémantique : sélectionne les top 7 pages
  (about, team, services, clients, technology, news)
     │
PHASE 4 — Scraper2
  Scrape chaque page sélectionnée
  Même méthode héritée de Scraper1 (crawl4ai ou flaresolverr)
     │
PHASE 5 — Nettoyage
  clean_markdown : supprime images, nav, footer légal
  extract_paragraphs : segmente en blocs texte propres
  → secondary_data prêt pour enrichissement NLP
```

---

## Installation

```bash
pip install crawl4ai sentence-transformers markdownify requests
crawl4ai-setup
```

### Télécharger le modèle multilingue (une seule fois)
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### FlareSolverr (optionnel, pour les sites avec Cloudflare)
```bash
docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
```

---

## Utilisation

```bash
# URL unique
python Pipeline.py --url https://www.biat.com.tn
python Pipeline.py --url biat.com.tn          # https:// ajouté automatiquement

# Batch (fichier texte, 1 URL par ligne)
python Pipeline.py --batch urls.txt

# Reprendre un batch interrompu
python Pipeline.py --batch urls.txt --resume
```

### Format urls.txt
```
# Banques Tunisiennes
https://www.biat.com.tn
https://www.bh.com.tn

# Consulting IT
https://www.vermeg.com
https://www.telnet.tn
```

---

## Configuration (config.py)

| Paramètre | Défaut | Description |
|---|---|---|
| `CRAWL4AI_TIMEOUT` | 45000 | Timeout scraping en ms |
| `CRAWL4AI_DELAY` | 6 | Attente après chargement page (s) |
| `DELAY_BETWEEN_URLS_MIN` | 2.0 | Pause min entre pages internes (s) |
| `DELAY_BETWEEN_URLS_MAX` | 5.0 | Pause max entre pages internes (s) |
| `SCORER_TOP_K` | 7 | Max pages internes sélectionnées |
| `SCORER_MAX_PER_CAT` | 1 | Max pages par catégorie |
| `STOP_ON_ERROR` | False | Arrêter le batch si un site échoue |

---

## Format du JSON de sortie

```json
{
  "website_url":      "https://www.biat.com.tn",
  "scrape_method":    "crawl4ai",
  "country":          "Tunisia",
  "email":            "contact@biat.com.tn",
  "phone":            "+216 71 188 000",
  "linkedin":         "https://www.linkedin.com/company/biat",
  "logo_url":         "https://...",
  "address":          "70-72, Avenue Habib Bourguiba, Tunis",

  "welcome_data": {
    "clean_text":  "La BIAT est une banque tunisienne...",
    "paragraphs":  ["La BIAT est...", "Fondée en 1976..."]
  },

  "scored_navigation": {
    "about":    {"url": "https://.../presentation-generale", "score": 0.445},
    "team":     {"url": "https://.../direction-generale",    "score": 0.531},
    "services": {"url": "https://.../nos-metiers",           "score": 0.421}
  },

  "secondary_data": {
    "about": {
      "clean_text": "La BIAT, Banque Internationale Arabe de Tunisie...",
      "paragraphs": ["La BIAT est...", "Notre mission..."]
    },
    "team": {
      "clean_text": "M. Ismail Mabrouk, Directeur Général...",
      "paragraphs": ["M. Ismail Mabrouk..."]
    },
    "services": { "clean_text": "...", "paragraphs": [...] }
  },

  "company_name":    null,
  "description":     null,
  "services":        null,
  "team_leaders":    null,
  "founded_year":    null,
  "employees_count": null
}
```

> Les champs `null` seront remplis par le module d'enrichissement NLP (Phase 6 — à venir).

---

## Modèle NLP — Scoring sémantique

Le scorer utilise **`paraphrase-multilingual-MiniLM-L12-v2`** de sentence-transformers.

- Entraîné sur 50 langues dont FR/EN
- Taille : 118MB, CPU-friendly
- Fonctionne nativement sur le français (BIAT, Telecom, Banque...)
- Anchors enrichis par secteur : Banque, Assurance, Consulting IT, Telecom

### Catégories cibles B2B
| Catégorie | Ce qu'on cherche |
|---|---|
| `about` | Présentation, histoire, mission, valeurs |
| `team` | Dirigeants, DG, PDG, comité de direction |
| `services` | Offres, produits, expertises, métiers |
| `clients` | Références clients, témoignages, cas d'usage |
| `technology` | Stack technique, méthodo, transformation digitale |
| `news` | Actualités, presse, publications |

---

## Prochaines étapes

- [ ] **Phase 6** : Enrichissement NLP (Ollama/Mistral local)
  - Extraire `company_name`, `description`, `services`, `team_leaders`
- [ ] **Storage** : MongoDB (raw_bundles + companies)
- [ ] **Sources additionnelles** : LinkedIn scraper, Finance, News
