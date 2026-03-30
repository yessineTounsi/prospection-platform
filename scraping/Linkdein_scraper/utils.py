import asyncio
import random


async def human_delay(min_ms=800, max_ms=2500):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def slow_scroll(page, steps=5):
    for _ in range(steps):
        await page.mouse.wheel(0, random.randint(300, 600))
        await human_delay(400, 900)


def clean_text(text) -> str:
    if not text:
        return ""
    text = str(text).strip()
    text = " ".join(text.split())
    text = text.replace("\u200b", "").replace("\xa0", " ")
    return text


def clean_url(url) -> str:
    if not url:
        return ""
    return url.split("?")[0].rstrip("/")