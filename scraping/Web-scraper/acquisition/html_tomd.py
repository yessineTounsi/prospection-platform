from markdownify import markdownify as md

def html_to_markdown(html: str) -> str:
    return md(html)