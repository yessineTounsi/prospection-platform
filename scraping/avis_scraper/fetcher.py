# fetcher.py — Requêtes HTTP, recherche et sélection d'entreprise

import re
import json
import requests
from bs4 import BeautifulSoup
from config import HEADERS


def fetch_page(url: str):
    """Télécharge une page et retourne un objet BeautifulSoup."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.exceptions.HTTPError as e:
        print(f"  ✗  Erreur HTTP {e.response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"  ✗  Connexion impossible")
    except requests.exceptions.Timeout:
        print(f"  ✗  Timeout")
    return None


def rechercher_entreprise(nom: str) -> list:
    """
    Cherche les entreprises sur Trustpilot correspondant au nom saisi.
    Retourne une liste de dicts : { nom, slug, url, nb_avis, note }
    """
    search_url = f"https://fr.trustpilot.com/search?query={requests.utils.quote(nom)}"
    print(f"\n  🔎  Recherche de '{nom}' sur Trustpilot…")

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ✗  Erreur : {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    resultats = []

    # ── Méthode 1 : navigation JSON propre dans __NEXT_DATA__ ─────────────────
    next_script = soup.find("script", {"id": "__NEXT_DATA__"})
    if next_script:
        try:
            nd = json.loads(next_script.string or "")

            def find_business_units(obj, depth=0):
                """Parcourt le JSON récursivement pour trouver les entreprises."""
                if depth > 10 or not isinstance(obj, (dict, list)):
                    return []
                found = []
                if isinstance(obj, list):
                    for item in obj:
                        found.extend(find_business_units(item, depth + 1))
                elif isinstance(obj, dict):
                    if (
                        "displayName" in obj
                        and "identifyingName" in obj
                        and isinstance(obj.get("displayName"), str)
                        and len(obj.get("displayName", "")) > 1
                    ):
                        nb_reviews = 0
                        rev = obj.get("numberOfReviews")
                        if isinstance(rev, dict):
                            nb_reviews = rev.get("total", 0)
                        elif isinstance(rev, int):
                            nb_reviews = rev

                        trust_score = obj.get("trustScore", "?")
                        note_str = str(trust_score).replace(".", ",") if trust_score != "?" else "?"

                        found.append({
                            "nom":     obj["displayName"],
                            "slug":    obj["identifyingName"],
                            "url":     f"https://fr.trustpilot.com/review/{obj['identifyingName']}",
                            "nb_avis": str(nb_reviews) if nb_reviews else "?",
                            "note":    note_str,
                        })
                    else:
                        for v in obj.values():
                            found.extend(find_business_units(v, depth + 1))
                return found

            units = find_business_units(nd)

            seen_slugs = set()
            for u in units:
                if u["slug"] not in seen_slugs:
                    seen_slugs.add(u["slug"])
                    resultats.append(u)
                if len(resultats) >= 8:
                    break

            if resultats:
                return resultats

        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    # ── Méthode 2 : parsing HTML fallback ─────────────────────────────────────
    seen = set()
    for card in soup.find_all("a", href=re.compile(r"/review/")):
        href = card.get("href", "")
        slug_m = re.search(r"/review/([^/?#]+)", href)
        if not slug_m or slug_m.group(1) in seen:
            continue
        slug_val = slug_m.group(1)
        seen.add(slug_val)

        nom_val = slug_val
        for tag in card.find_all(["h2", "h3", "p", "span"]):
            t = tag.get_text(strip=True)
            if t and len(t) > 2 and not re.match(r"^[\d,\.]+$", t):
                nom_val = t
                break

        resultats.append({
            "nom":     nom_val,
            "slug":    slug_val,
            "url":     f"https://fr.trustpilot.com/review/{slug_val}",
            "nb_avis": "?",
            "note":    "?",
        })

    return resultats[:8]


def choisir_entreprise(resultats: list):
    """Affiche la liste des résultats avec URL et laisse l'utilisateur choisir."""
    if not resultats:
        print("  ✗  Aucun résultat.")
        return None

    print(f"\n  {'─'*70}")
    print(f"  {'#':<4} {'Entreprise':<28} {'Note':<7} {'Avis':<10} URL")
    print(f"  {'─'*70}")
    for i, r in enumerate(resultats, 1):
        print(f"  {i:<4} {r['nom']:<28} {r['note']:<7} {r['nb_avis']:<10} {r['url']}")
    print(f"  {'─'*70}")

    while True:
        choix = input(f"\n  → Choisir un numéro [1-{len(resultats)}] : ").strip()
        if choix.isdigit() and 1 <= int(choix) <= len(resultats):
            return resultats[int(choix) - 1]
        print(f"  ⚠  Entre un numéro entre 1 et {len(resultats)}")