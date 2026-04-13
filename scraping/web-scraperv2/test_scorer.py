import sys
sys.path.insert(0, ".")

from navigation.link_extractor import extract_links
from navigation.llm_scorer import LLMScorer

md_path = "output/md/www_confoline_com.md"
with open(md_path, encoding="utf-8") as f:
    markdown = f.read()

links = extract_links(markdown, base_url="https://www.confoline.com")
print(f"\n{len(links)} liens extraits :")
for l in links:
    print(f"  [{l.text}] {l.url}")

print("\nScoring LLM...")
scorer = LLMScorer()
results = scorer.score_links(links, base_url="https://www.confoline.com")
print(f"\n{len(results)} liens classifiés :")
for r in results:
    print(f"  [{r.category}] {r.link.url} (score={r.score})")
