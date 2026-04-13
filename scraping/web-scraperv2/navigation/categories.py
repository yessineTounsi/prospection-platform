"""
navigation/categories.py
========================
Catégories B2B — version définitive
Modèle : paraphrase-multilingual-MiniLM-L12-v2

Rôle de ce scraper dans le pipeline global :
  Web scraper  → about, team, services, clients, contact, technology, partners
  LinkedIn     → dirigeants (enrichissement)
  Finance      → taille, année fondation (enrichissement)
  News scraper → actualités (source dédiée — pas ici)

Catégories actives (7) :
  priority 1 — about      : pays, secteur, taille, année fondation
  priority 2 — team       : dirigeants, personnes clés (CEO, DSI, RSSI...)
  priority 3 — services   : offres, produits, expertises
  priority 4 — clients    : références, cas clients
  priority 5 — contact    : email, phone, linkedin URL dédiés
  priority 6 — technology : stack, infra, cloud (utile Confoline)
  priority 7 — partners   : certifications éditeurs, partenariats

  news → supprimé (news scraper dédié)
"""

from dataclasses import dataclass


@dataclass
class Category:
    name:      str
    anchors:   list
    threshold: float = 0.30
    priority:  int   = 5


CATEGORIES = [

    # ── 1. ABOUT ─────────────────────────────────────────────────────────────
    Category(
        name="about",
        priority=1,
        threshold=0.33,
        anchors=[
            # EN
            "about us", "who we are", "our story", "company overview",
            "our history", "our mission and vision", "our values",
            "company profile", "our group", "our identity",
            "corporate governance", "ownership structure",
            "investor relations", "shareholders", "annual report",
            # FR — générique
            "qui sommes nous", "a propos de nous", "notre histoire",
            "notre mission", "notre vision", "presentation de l entreprise",
            "notre entreprise", "nos valeurs", "notre groupe",
            "notre societe", "presentation generale", "notre raison d etre",
            # FR — gouvernance
            "relations investisseurs", "actionnaires", "gouvernance",
            "rapport annuel", "structure du groupe", "organigramme du groupe",
            "gouvernance d entreprise",
            # FR — banque / finance
            "presentation de la banque", "presentation du groupe bancaire",
            "notre etablissement financier", "historique de la banque",
            "gouvernance de la banque", "organes de gouvernance",
            # FR — consulting IT / ESN
            "presentation du cabinet", "notre cabinet de conseil",
            "notre agence IT", "notre expertise depuis",
            # FR — telecom / industrie
            "presentation de l operateur", "notre groupe industriel",
        ]
    ),

    # ── 2. TEAM ──────────────────────────────────────────────────────────────
    # Inclut pages recrutement — contiennent souvent organigramme et dirigeants
    Category(
        name="team",
        priority=2,
        threshold=0.33,
        anchors=[
            # EN — leadership
            "our team", "leadership team", "management team",
            "executive team", "executive committee",
            "chief executive officer CEO", "chief information officer CIO",
            "chief technology officer CTO", "chief security officer CISO",
            "chief digital officer CDO", "chief operating officer COO",
            "chief financial officer CFO",
            "IT director", "head of infrastructure", "head of security",
            "VP engineering", "VP technology",
            "founders", "our experts", "key people", "meet the team",
            # EN — recrutement (contient noms et titres managers)
            "join our team", "work with us", "careers",
            "our culture", "meet our people", "why join us",
            # FR — direction
            "notre equipe", "notre direction", "equipe dirigeante",
            "comite de direction", "comite executif", "fondateurs",
            "direction generale", "directeur general", "PDG", "DG",
            # FR — décideurs IT
            "directeur des systemes d information", "DSI",
            "directeur technique", "directeur informatique",
            "responsable infrastructure", "responsable securite", "RSSI",
            "responsable cybersecurite", "directeur digital",
            "responsable transformation digitale", "directeur cloud",
            # FR — recrutement
            "rejoindre notre equipe", "travailler avec nous",
            "la vie dans l entreprise", "notre culture d entreprise",
            "temoignages de nos collaborateurs", "pourquoi nous rejoindre",
            "recrutement", "carrieres", "emploi",
            # FR — banque / finance
            "le mot du directeur general", "direction de la banque",
            "membres du comite de direction",
            # FR — consulting / ESN
            "nos associes", "nos partners", "les co-fondateurs",
            "notre equipe technique", "nos managers",
        ]
    ),

    # ── 3. SERVICES ──────────────────────────────────────────────────────────
    Category(
        name="services",
        priority=3,
        threshold=0.35,
        anchors=[
            # EN
            "our services", "what we offer", "solutions", "our products",
            "service catalog", "offerings", "expertise", "capabilities",
            "our solutions portfolio",
            # FR — générique
            "nos services", "nos solutions", "nos offres", "nos produits",
            "catalogue de services", "nos expertises", "nos prestations",
            "domaines d activite", "nos competences", "notre offre",
            "nos metiers",
            # FR — banque / finance
            "nos offres bancaires", "banque de detail",
            "banque des entreprises", "produits bancaires",
            "credit immobilier", "epargne et placement",
            "financement des entreprises", "gestion de patrimoine",
            # FR — assurance
            "nos produits d assurance", "assurance entreprise",
            # FR — consulting IT / ESN
            "conseil en transformation digitale",
            "integration de systemes", "developpement logiciel sur mesure",
            "managed services", "outsourcing IT", "infogerance",
            "audit informatique",
            # FR — telecom
            "nos forfaits", "offres entreprises", "solutions connectivite",
            # FR — industrie
            "nos produits industriels", "nos solutions industrielles",
        ]
    ),

    # ── 4. CLIENTS ───────────────────────────────────────────────────────────
    Category(
        name="clients",
        priority=4,
        threshold=0.33,
        anchors=[
            # EN
            "our clients", "our customers", "case studies", "references",
            "success stories", "customer testimonials", "who we work with",
            "portfolio", "they trust us",
            # FR
            "nos clients", "nos references", "etudes de cas",
            "temoignages", "cas clients", "ils nous font confiance",
            "references clients", "nos realisations",
            "temoignages clients", "avis clients", "nos cas d usage",
            # FR — consulting / ESN
            "nos missions", "nos projets realises",
            "clients references", "nos clients grands comptes",
        ]
    ),

    # ── 5. CONTACT ───────────────────────────────────────────────────────────
    Category(
        name="contact",
        priority=5,
        threshold=0.32,
        anchors=[
            # EN
            "contact us", "get in touch", "reach us",
            "our offices", "office locations", "headquarters",
            "contact form", "our address", "find us",
            # FR
            "contactez nous", "nous contacter", "prendre contact",
            "formulaire de contact", "nous joindre",
            "nos coordonnees", "nos bureaux", "siege social",
            "adresse du siege", "nos agences", "nos locaux",
            "plan d acces", "comment nous contacter",
            # FR — banque
            "agences bancaires", "reseau d agences",
            "service client banque", "trouver une agence",
            # FR — consulting
            "demande de devis", "prendre rendez vous",
            "echanger avec nos equipes",
            # FR — telecom
            "service client telecom", "centre d appel",
        ]
    ),

    # ── 6. TECHNOLOGY ────────────────────────────────────────────────────────
    # Utile pour Confoline : révèle le stack = surface d'adressabilité produit
    Category(
        name="technology",
        priority=6,
        threshold=0.36,
        anchors=[
            # EN
            "technology stack", "our technology", "tech stack",
            "infrastructure", "cloud infrastructure", "IT infrastructure",
            "DevOps", "observability", "monitoring", "APM",
            "log management", "network monitoring", "cloud monitoring",
            "cybersecurity", "SIEM", "SOC", "Kubernetes",
            "hybrid cloud", "multi-cloud", "cloud native",
            "digital transformation", "IT modernization",
            "technical expertise", "methodology", "platforms",
            # FR
            "notre technologie", "stack technique", "nos outils",
            "infrastructure informatique", "infrastructure cloud",
            "ingenierie logicielle", "notre approche DevOps",
            "supervision informatique", "monitoring applicatif",
            "observabilite", "gestion des logs",
            "cybersecurite", "securite informatique", "securite du SI",
            "SOC", "SIEM", "audit de securite", "securite cloud",
            "transformation numerique", "transformation digitale",
            "modernisation du SI", "migration cloud",
            "cloud AWS Azure GCP", "architecture microservices",
            "intelligence artificielle IA", "big data analytics",
            "banque digitale", "open banking", "fintech",
            "infrastructure telecom", "industrie 4.0",
        ]
    ),

    # ── 7. PARTNERS ──────────────────────────────────────────────────────────
    # Certifications éditeurs = maturité IT + stack visible
    Category(
        name="partners",
        priority=7,
        threshold=0.36,
        anchors=[
            # EN
            "our partners", "technology partners", "ecosystem",
            "certifications", "partnerships", "alliances",
            "partner network", "certified partner",
            "gold partner", "platinum partner", "awards",
            # FR
            "nos partenaires", "partenariats", "notre ecosysteme",
            "partenaires technologiques", "nos certifications",
            "nos accreditations", "partenaires strategiques",
            # FR — IT / intégrateur
            "partenaires editeurs", "certifie microsoft",
            "certifie AWS", "certifie Google Cloud", "certifie Azure",
            "certifie Datadog", "certifie Dynatrace", "certifie Splunk",
            "certifie ServiceNow", "partenaire integrateur",
            # FR — qualité / industrie
            "certifications qualite", "norme ISO", "certification ISO",
        ]
    ),

]

CATEGORIES_BY_NAME = {c.name: c for c in CATEGORIES}

SCORER_CONFIG = {
    "model_name":       "paraphrase-multilingual-MiniLM-L12-v2",
    "context_weight":   0.3,
    "top_k_anchors":    3,
    "ambiguity_margin": 0.04,
}