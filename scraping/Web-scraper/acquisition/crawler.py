import random
import ssl
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from config import USER_AGENTS, CRAWL4AI_HEADLESS, CRAWL4AI_DELAY, CRAWL4AI_TIMEOUT

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

async def crawl_site(url: str) -> str | None:
    browser_config = BrowserConfig(
        headless=CRAWL4AI_HEADLESS,
        viewport_width=1280,
        viewport_height=800,
        user_agent=random.choice(USER_AGENTS)
    )
    run_config = CrawlerRunConfig(
        word_count_threshold=10,
        exclude_external_links=False,
        exclude_social_media_links=False,
        wait_until="domcontentloaded",
        delay_before_return_html=CRAWL4AI_DELAY,
        page_timeout=CRAWL4AI_TIMEOUT,
    )
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url, config=run_config)
        if result.success:
            return result.markdown
        print(f"❌ Crawl4AI error : {result.error_message}")
        return None