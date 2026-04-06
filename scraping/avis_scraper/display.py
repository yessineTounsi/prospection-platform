# display.py — Affichage terminal et sauvegarde JSON / CSV

import re
import json
import csv
from datetime import datetime


# ─── Affichage terminal ────────────────────────────────────────────────────────

def afficher_resultats(entreprise: dict, score: dict, resume: dict, commentaires: list):
    W = 66
    print("\n" + "═" * W)
    print(f"  {entreprise['nom'].upper()}")
    print(f"  {entreprise['url']}")
    print("═" * W)

    # Score
    note    = score.get("note_globale") or "N/A"
    mention = score.get("mention") or "N/A"
    nb      = score.get("nombre_avis") or "N/A"
    print(f"\n  ⭐  Note : {note} / 5  —  {mention}  —  {nb} avis\n")

    bar_order = ["5 étoiles", "4 étoiles", "3 étoiles", "2 étoiles", "1 étoile"]
    bar_icons = {
        "5 étoiles": "🟢", "4 étoiles": "🟡",
        "3 étoiles": "🟡", "2 étoiles": "🟠", "1 étoile": "🔴"
    }
    dist = score.get("distribution_etoiles", {})
    for label in bar_order:
        val = dist.get(label) or "N/A"
        pct_num = 0
        if val != "N/A":
            m = re.search(r"(\d+)%", val)
            if m:
                pct_num = int(m.group(1))
        bar = "█" * (pct_num // 5) + "░" * (20 - pct_num // 5)
        print(f"    {bar_icons[label]}  {label:<12}  {bar}  {val}")

    # Résumé IA
    print("\n" + "─" * W)
    print("  📋  RÉSUMÉ IA")
    print("─" * W)
    texte = resume.get("texte_resume")
    if texte:
        for line in texte.split("\n"):
            if not line.strip():
                print()
                continue
            words, row = line.split(), "  "
            for w in words:
                if len(row) + len(w) + 1 > 64:
                    print(row)
                    row = "  " + w + " "
                else:
                    row += w + " "
            if row.strip():
                print(row)
    else:
        print("  (Résumé IA non disponible)")

    # Commentaires
    print("\n" + "─" * W)
    print(f"  💬  {len(commentaires)} DERNIERS COMMENTAIRES (du plus récent)")
    print("─" * W)
    stars_map = {
        "1": "★☆☆☆☆", "2": "★★☆☆☆", "3": "★★★☆☆",
        "4": "★★★★☆", "5": "★★★★★"
    }
    for i, c in enumerate(commentaires, 1):
        note_str = stars_map.get(c["note"], f"note:{c['note'] or '?'}")
        print(f"\n  [{i:02d}] {(c['auteur'] or 'Anonyme'):<28} {c['date']}")
        print(f"        {note_str}")
        if c["titre"]:
            print(f"        📌 {c['titre']}")
        contenu = (c["contenu"][:220] + "…") if len(c["contenu"]) > 220 else c["contenu"]
        print(f"        {contenu}")
        if c["entreprise_a_repondu"]:
            print(f"        💬 L'entreprise a répondu")

    print("\n" + "═" * W)


# ─── Sauvegarde JSON + CSV ─────────────────────────────────────────────────────

def save_results(entreprise: dict, score: dict, resume: dict, commentaires: list):
    slug = re.sub(r"[^\w]", "_", entreprise["slug"].strip("/"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    resultats = {
        "entreprise":   entreprise,
        "scraped_at":   timestamp,
        "score":        score,
        "resume_ia":    resume,
        "commentaires": commentaires,
    }

    json_file = f"trustpilot_{slug}_{timestamp}.json"
    csv_file  = f"trustpilot_{slug}_{timestamp}.csv"

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)

    if commentaires:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=commentaires[0].keys())
            writer.writeheader()
            writer.writerows(commentaires)

    print(f"\n  💾  JSON → {json_file}")
    print(f"  💾  CSV  → {csv_file}")