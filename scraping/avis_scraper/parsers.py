# parsers.py — Extraction du score, résumé IA et commentaires

import re
import json


# ─── 1. SCORE + DISTRIBUTION DES ÉTOILES ──────────────────────────────────────

def scrape_score(soup) -> dict:
    """
    Extrait la note globale, la mention, le nombre d'avis
    et la distribution des étoiles (vrais counts depuis __NEXT_DATA__).
    """
    score = {
        "note_globale": None,
        "mention": None,
        "nombre_avis": None,
        "distribution_etoiles": {
            "5 étoiles": None,
            "4 étoiles": None,
            "3 étoiles": None,
            "2 étoiles": None,
            "1 étoile":  None,
        },
    }

    # ── Priorité 1 : __NEXT_DATA__ ────────────────────────────────────────────
    next_script = soup.find("script", {"id": "__NEXT_DATA__"})
    if next_script:
        try:
            nd = json.loads(next_script.string or "")
            text_nd = json.dumps(nd, ensure_ascii=False)

            m = re.search(r'"trustScore"\s*:\s*([\d.]+)', text_nd)
            if m:
                score["note_globale"] = m.group(1).replace(".", ",")

            m = re.search(r'"numberOfReviews"\s*:\s*\{[^}]*"total"\s*:\s*(\d+)', text_nd)
            if m:
                score["nombre_avis"] = f"{int(m.group(1)):,}".replace(",", " ")

            m = re.search(r'"starsString"\s*:\s*"([^"]+)"', text_nd)
            if m:
                score["mention"] = m.group(1)

            # Distribution : lire les counts bruts et calculer les vrais %
            dist_block = re.search(r'"ratingDistribution"\s*:\s*(\[[^\]]+\])', text_nd)
            if dist_block:
                entries = re.findall(
                    r'"stars"\s*:\s*(\d)\s*,\s*"count"\s*:\s*(\d+)',
                    dist_block.group(1)
                )
                if not entries:
                    entries = [
                        (s, c) for c, s in re.findall(
                            r'"count"\s*:\s*(\d+)\s*,\s*"stars"\s*:\s*(\d)',
                            dist_block.group(1)
                        )
                    ]
                if entries:
                    total = sum(int(c) for _, c in entries)
                    count_map = {str(s): int(c) for s, c in entries}
                    label_map = {
                        "5": "5 étoiles", "4": "4 étoiles",
                        "3": "3 étoiles", "2": "2 étoiles", "1": "1 étoile"
                    }
                    for star, key in label_map.items():
                        count = count_map.get(star, 0)
                        pct = round(count / total * 100) if total else 0
                        score["distribution_etoiles"][key] = f"{pct}%  ({count} avis)"

        except (json.JSONDecodeError, AttributeError):
            pass

    # ── Priorité 2 : JSON-LD fallback ─────────────────────────────────────────
    if not score["note_globale"]:
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                agg = data.get("aggregateRating", {})
                if agg.get("ratingValue"):
                    score["note_globale"] = str(agg["ratingValue"]).replace(".", ",")
                    score["nombre_avis"]  = str(agg.get("reviewCount", ""))
                    break
            except (json.JSONDecodeError, AttributeError):
                continue

    # ── Priorité 3 : HTML brut fallback ───────────────────────────────────────
    if not score["mention"]:
        tag = soup.find(string=re.compile(
            r"^(Excellent|Bien|Moyen|Mauvais|Très mauvais)$", re.I
        ))
        if tag:
            score["mention"] = tag.strip()

    if not score["nombre_avis"]:
        tag = soup.find(string=re.compile(r"\d[\d\s,\.]*\s*(k\s+)?avis", re.I))
        if tag:
            score["nombre_avis"] = tag.strip()

    return score


# ─── 2. RÉSUMÉ IA ──────────────────────────────────────────────────────────────

def scrape_resume(soup) -> dict:
    """
    Extrait le résumé IA généré par Trustpilot.
    Déduplication renforcée pour éviter les doublons.
    """
    resume = {"texte_resume": None}

    # Méthode 1 : data-testid connu
    section = (
        soup.find(attrs={"data-testid": "review-summary"})
        or soup.find(attrs={"data-testid": "reviews-summary"})
        or soup.find(attrs={"data-testid": "ai-summary"})
    )

    # Méthode 2 : titre "Résumé des avis"
    if not section:
        titre = soup.find(string=re.compile(r"R[ée]sum[ée]\s+des\s+avis", re.I))
        if titre:
            parent = titre.find_parent()
            for _ in range(6):
                if parent and len(parent.get_text(strip=True)) > 200:
                    section = parent
                    break
                parent = parent.find_parent() if parent else None

    # Méthode 3 : heuristique contenu
    if not section:
        for div in soup.find_all("div"):
            t = div.get_text(strip=True)
            if "basé sur les avis" in t.lower() and 200 < len(t) < 5000:
                section = div
                break

    if section:
        raw = []
        for p in section.find_all(["p", "span"]):
            t = p.get_text(strip=True)
            if len(t) > 100 and not re.match(r"voir (plus|moins)", t, re.I):
                raw.append(t)

        # Garder uniquement les textes non inclus dans un autre plus long
        unique = []
        for p in sorted(raw, key=len, reverse=True):
            if not any(p in u for u in unique):
                unique.append(p)

        resume["texte_resume"] = "\n\n".join(unique) if unique else None

    return resume


# ─── 3. COMMENTAIRES ───────────────────────────────────────────────────────────

def scrape_commentaires(soup, nb: int = 15) -> list:
    """
    Extrait tous les commentaires de la page, les trie du plus récent
    au plus ancien, et retourne les nb premiers.
    """
    cards = (
        soup.find_all(attrs={"data-service-review-card-paper": True})
        or soup.find_all(attrs={"data-testid": "review-card"})
        or soup.find_all("article")
    )
    print(f"  → {len(cards)} carte(s) d'avis trouvée(s) sur la page")

    commentaires = []
    for card in cards:
        avis = {
            "auteur": "",
            "date": "",
            "date_iso": "",
            "note": "",
            "titre": "",
            "contenu": "",
            "entreprise_a_repondu": False,
        }

        # Auteur
        for attr in [
            {"data-consumer-name-typography": True},
            {"data-testid": "consumer-name"},
        ]:
            tag = card.find(attrs=attr)
            if tag:
                avis["auteur"] = tag.get_text(strip=True)
                break

        # Date
        time_tag = card.find("time")
        if time_tag:
            avis["date_iso"] = time_tag.get("datetime", "")
            avis["date"] = time_tag.get_text(strip=True)

        # Note — 3 tentatives (Trustpilot a changé ses sélecteurs)
        note_found = False

        for attr in [
            {"data-service-review-rating": True},
            {"data-testid": "review-rating"},
        ]:
            tag = card.find(attrs=attr)
            if tag:
                val = tag.get("data-service-review-rating") or tag.get("aria-label", "")
                m = re.search(r"(\d)", str(val))
                if m:
                    avis["note"] = m.group(1)
                    note_found = True
                    break

        if not note_found:
            for img in card.find_all("img"):
                alt = img.get("alt", "") or img.get("aria-label", "")
                m = re.search(r"(\d)\s*(é|e)toile", alt, re.I) or re.search(r"rated?\s+(\d)", alt, re.I)
                if m:
                    avis["note"] = m.group(1)
                    note_found = True
                    break

        if not note_found:
            for tag in card.find_all(attrs={"aria-label": re.compile(r"étoile|star", re.I)}):
                aria = tag.get("aria-label", "")
                m = re.search(r"(\d)\s*(é|e)toile|rated?\s+(\d)", aria, re.I)
                if m:
                    avis["note"] = m.group(1) or m.group(3)
                    break

        # Titre — 3 tentatives
        title_found = False

        for attr in [
            {"data-service-review-title-typography": True},
            {"data-testid": "review-title"},
        ]:
            tag = card.find(attrs=attr)
            if tag:
                avis["titre"] = tag.get_text(strip=True)
                title_found = True
                break

        if not title_found:
            for a in card.find_all("a", href=True):
                h2 = a.find("h2")
                if h2:
                    avis["titre"] = h2.get_text(strip=True)
                    title_found = True
                    break

        if not title_found:
            h2 = card.find("h2")
            if h2:
                avis["titre"] = h2.get_text(strip=True)

        # Contenu
        content_found = False
        for attr in [
            {"data-service-review-text-typography": True},
            {"data-testid": "review-content"},
        ]:
            tag = card.find(attrs=attr)
            if tag:
                avis["contenu"] = tag.get_text(strip=True)
                content_found = True
                break

        if not content_found:
            texts = sorted(
                [p.get_text(strip=True) for p in card.find_all("p")],
                key=len, reverse=True
            )
            if texts:
                avis["contenu"] = texts[0]

        # Réponse entreprise
        avis["entreprise_a_repondu"] = bool(
            card.find(string=re.compile(r"l.entreprise a répondu", re.I))
            or card.find(attrs={"data-testid": "company-reply"})
        )

        commentaires.append(avis)

    # Trier du plus récent au plus ancien par date ISO
    commentaires.sort(
        key=lambda x: x["date_iso"] if x["date_iso"] else "0000",
        reverse=True
    )

    print(f"  → {len(commentaires[:nb])} commentaires les plus récents sélectionnés")
    return commentaires[:nb]