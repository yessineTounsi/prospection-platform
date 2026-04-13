import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from acquisition.scraper1 import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

URLS = [
    # Banques
    "https://www.biat.com.tn",
    "https://www.attijaribank.com.tn",
    "https://www.bnpparibas.com",
    "https://www.societegenerale.com",
    "https://www.cib.com.eg",
    # Assurances
    "https://www.star.com.tn",
    "https://www.gat.com.tn",
    "https://www.axa.com",
    "https://www.allianz.com",
    # Telecom
    "https://www.ooredoo.tn",
    "https://www.tunisietelecom.tn",
    "https://www.orange.com",
    "https://www.orange.tn",
    # E-commerce
    "https://www.jumia.com.tn",
    "https://www.mytek.tn",
    "https://www.tunisianet.com.tn",
    # Industrie
    "https://www.serept.com.tn",
    "https://www.steg.com.tn",
    # Public
    "https://www.cnss.tn",
    "https://www.cnam.tn",
]


async def main():
    stats   = {"ok": 0, "fail": 0}
    results = []

    sep = "=" * 60
    print("")
    print(sep)
    print(f"Scraping {len(URLS)} welcome pages...")
    print(sep)
    print("")

    for i, url in enumerate(URLS, 1):
        print(f"[{i:02d}/{len(URLS)}] {url}")
        try:
            result = await run(url)
            if result:
                md_path, method = result
                print(f"        OK [{method}] -> {md_path}")
                print("")
                stats["ok"] += 1
                results.append({"url": url, "md_path": str(md_path), "method": method})
            else:
                print("        FAIL")
                print("")
                stats["fail"] += 1
                results.append({"url": url, "md_path": None, "method": None})
        except Exception as e:
            print(f"        ERREUR : {e}")
            print("")
            stats["fail"] += 1
            results.append({"url": url, "md_path": None, "method": None})

    print(sep)
    print("Termine !")
    print(f"  OK   : {stats['ok']}/{len(URLS)}")
    print(f"  FAIL : {stats['fail']}/{len(URLS)}")
    print("  Fichiers .md dans : output/md/")
    print(sep)
    print("")

    ok_results = [r for r in results if r["md_path"]]
    if ok_results:
        print("Fichiers produits :")
        for r in ok_results:
            print(f"  {r['md_path']}")
    print("")


if __name__ == "__main__":
    asyncio.run(main())