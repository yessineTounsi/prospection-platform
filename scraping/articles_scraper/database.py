import sqlite3
import json

from config import DB_NAME


# ─────────────────────────────────────────────
#  CONNEXION
# ─────────────────────────────────────────────

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────
#  INITIALISATION DU SCHÉMA
# ─────────────────────────────────────────────

def init_db():
    """Crée les tables companies et articles si elles n'existent pas."""
    conn   = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            domain       TEXT,
            company_url  TEXT UNIQUE,
            description  TEXT,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id           INTEGER NOT NULL,
            titre                TEXT,
            source               TEXT,
            date_publication     TEXT,
            url                  TEXT UNIQUE,
            langue               TEXT,
            auteur               TEXT,
            extrait              TEXT,
            texte_complet        TEXT,
            mots_cles            TEXT,
            categories_detectees TEXT,
            article_type         TEXT,
            date_scraping        TEXT,
            relevance_score      REAL,
            relevance_info       TEXT,
            source_type          TEXT,
            titre_rss            TEXT,
            date_rss             TEXT,
            source_rss           TEXT,
            created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
#  SAUVEGARDE D'UNE ENTREPRISE
# ─────────────────────────────────────────────

def save_company(company_info: dict, company_url: str) -> int:
    """
    Insère ou met à jour l'entreprise dans la table companies.
    Retourne l'ID de l'entreprise.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO companies (company_name, domain, company_url, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(company_url) DO UPDATE SET
            company_name = excluded.company_name,
            domain       = excluded.domain,
            description  = excluded.description
    """, (
        company_info.get("company_name"),
        company_info.get("domain"),
        company_url,
        company_info.get("description"),
    ))
    conn.commit()

    cursor.execute("SELECT id FROM companies WHERE company_url = ?", (company_url,))
    company_id = cursor.fetchone()[0]
    conn.close()
    return company_id


# ─────────────────────────────────────────────
#  SAUVEGARDE DES ARTICLES
# ─────────────────────────────────────────────

def save_articles_to_db(company_id: int, articles: list):
    """
    Insère ou met à jour les articles dans la table articles.
    Utilise ON CONFLICT(url) pour éviter les doublons.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()

    for article in articles:
        cursor.execute("""
            INSERT INTO articles (
                company_id, titre, source, date_publication, url, langue, auteur,
                extrait, texte_complet, mots_cles, categories_detectees,
                article_type, date_scraping, relevance_score, relevance_info,
                source_type, titre_rss, date_rss, source_rss
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                company_id           = excluded.company_id,
                titre                = excluded.titre,
                source               = excluded.source,
                date_publication     = excluded.date_publication,
                langue               = excluded.langue,
                auteur               = excluded.auteur,
                extrait              = excluded.extrait,
                texte_complet        = excluded.texte_complet,
                mots_cles            = excluded.mots_cles,
                categories_detectees = excluded.categories_detectees,
                article_type         = excluded.article_type,
                date_scraping        = excluded.date_scraping,
                relevance_score      = excluded.relevance_score,
                relevance_info       = excluded.relevance_info,
                source_type          = excluded.source_type,
                titre_rss            = excluded.titre_rss,
                date_rss             = excluded.date_rss,
                source_rss           = excluded.source_rss
        """, (
            company_id,
            article.get("titre"),
            article.get("source"),
            article.get("date_publication"),
            article.get("url"),
            article.get("langue"),
            article.get("auteur"),
            article.get("extrait"),
            article.get("texte_complet"),
            json.dumps(article.get("mots_cles", []),            ensure_ascii=False),
            json.dumps(article.get("categories_detectees", []), ensure_ascii=False),
            article.get("article_type"),
            article.get("date_scraping"),
            article.get("relevance_score"),
            json.dumps(article.get("relevance_info", {}),       ensure_ascii=False),
            article.get("source_type"),
            article.get("titre_rss"),
            article.get("date_rss"),
            article.get("source_rss"),
        ))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
#  LECTURE
# ─────────────────────────────────────────────

def get_articles_by_company(company_name: str) -> list:
    """
    Retourne tous les articles d'une entreprise (titre, url, source, date).
    Triés par date de création décroissante.
    """
    conn   = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.titre, a.url, a.source, a.date_publication
        FROM articles a
        JOIN companies c ON a.company_id = c.id
        WHERE c.company_name = ?
        ORDER BY a.created_at DESC
    """, (company_name,))

    rows = cursor.fetchall()
    conn.close()
    return rows