"""
Twitter / X Scraper — uses Nitter RSS mirrors (free, no API key needed).
Falls back through multiple Nitter instances automatically.
Only checks last 20 tweets per professor.
"""
import asyncio
import logging
from datetime import datetime

import httpx
import feedparser

from scrapers.base import BaseScraper, Finding

logger = logging.getLogger(__name__)

# Public Nitter instances — add/remove as they go up/down
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.unixfox.eu",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PhDMonitorBot/1.0; "
        "+https://github.com/Rahul-Verma97/PHD)"
    )
}

TIMEOUT   = 12
MAX_ITEMS = 20


class TwitterScraper(BaseScraper):
    async def scrape(self, professor: dict) -> list[Finding]:
        handle = professor.get("twitter_handle", "").lstrip("@")
        if not handle:
            return []

        feed = await self._fetch_nitter_rss(handle)
        if not feed:
            return []

        findings = []
        for entry in feed.entries[:MAX_ITEMS]:
            snippet = self._clean(getattr(entry, "summary", "") or entry.get("title", ""))
            url     = entry.get("link", f"https://twitter.com/{handle}")
            findings.append(self._make_finding(professor, "twitter", url, snippet))

        return findings

    # ── Internals ──────────────────────────────────────────────────────────────

    async def _fetch_nitter_rss(self, handle: str):
        async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT,
                                     follow_redirects=True) as client:
            for instance in NITTER_INSTANCES:
                rss_url = f"{instance}/{handle}/rss"
                try:
                    resp = await client.get(rss_url)
                    if resp.status_code == 200:
                        feed = feedparser.parse(resp.text)
                        if feed.entries:
                            logger.debug("Nitter RSS ok: %s via %s", handle, instance)
                            return feed
                except Exception as e:
                    logger.debug("Nitter %s failed for @%s: %s", instance, handle, e)
                await asyncio.sleep(0.5)

        logger.warning("All Nitter instances failed for @%s — skipping Twitter", handle)
        return None

    @staticmethod
    def _clean(text: str) -> str:
        """Strip HTML tags and collapse whitespace."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "lxml")
        return " ".join(soup.get_text(separator=" ").split())
