"""
RSS Scraper — checks professor-configured RSS feeds AND common RSS patterns.
Also parses Google Alerts RSS feeds (most powerful source for hiring announcements).
"""
import asyncio
import logging

import httpx
import feedparser

from scrapers.base import BaseScraper, Finding

logger = logging.getLogger(__name__)

# Common RSS path patterns to try for each professor website / lab page
RSS_PATTERNS = [
    "/feed",
    "/feed.xml",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/blog/feed",
    "/news/feed",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PhDMonitorBot/1.0; "
        "+https://github.com/Rahul-Verma97/PHD)"
    )
}

TIMEOUT   = 12
MAX_ITEMS = 30


class RSSScraper(BaseScraper):
    async def scrape(self, professor: dict) -> list[Finding]:
        rss_urls = self._build_rss_url_list(professor)
        findings = []

        async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT,
                                     follow_redirects=True) as client:
            for rss_url in rss_urls:
                try:
                    resp = await client.get(rss_url)
                    if resp.status_code != 200:
                        continue
                    feed = feedparser.parse(resp.text)
                    if not feed.entries:
                        continue

                    logger.debug("RSS ok: %s — %d entries", rss_url, len(feed.entries))
                    for entry in feed.entries[:MAX_ITEMS]:
                        snippet = self._entry_text(entry)
                        url     = entry.get("link", rss_url)
                        findings.append(
                            self._make_finding(professor, "rss", url, snippet)
                        )
                    break  # stop at first working RSS URL

                except Exception as e:
                    logger.debug("RSS fetch failed %s: %s", rss_url, e)
                await asyncio.sleep(0.5)

        # Also check Google Alert RSS if configured
        google_rss = professor.get("google_alert_rss", "")
        if google_rss:
            findings += await self._fetch_google_alert(professor, google_rss)

        return findings

    # ── Internals ──────────────────────────────────────────────────────────────

    def _build_rss_url_list(self, professor: dict) -> list[str]:
        urls = []

        # Explicit RSS feed first
        if professor.get("rss_feed"):
            urls.append(professor["rss_feed"])

        # Try patterns on website and lab page
        for base_key in ("website", "lab_page"):
            base = professor.get(base_key, "").rstrip("/")
            if base:
                for pat in RSS_PATTERNS:
                    urls.append(base + pat)

        return list(dict.fromkeys(urls))  # deduplicate while preserving order

    async def _fetch_google_alert(self, professor: dict, rss_url: str) -> list[Finding]:
        findings = []
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT,
                                         follow_redirects=True) as client:
                resp = await client.get(rss_url)
                if resp.status_code != 200:
                    return []
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:MAX_ITEMS]:
                    snippet = self._entry_text(entry)
                    url     = entry.get("link", rss_url)
                    findings.append(
                        self._make_finding(professor, "google_alert", url, snippet)
                    )
        except Exception as e:
            logger.debug("Google Alert RSS failed for %s: %s", professor["name"], e)
        return findings

    @staticmethod
    def _entry_text(entry) -> str:
        """Combine title + summary into a clean text snippet."""
        from bs4 import BeautifulSoup
        parts = []
        for attr in ("title", "summary", "content"):
            val = entry.get(attr, "")
            if isinstance(val, list):
                val = " ".join(v.get("value", "") for v in val)
            parts.append(str(val))
        raw = " ".join(parts)
        soup = BeautifulSoup(raw, "lxml")
        return " ".join(soup.get_text(separator=" ").split())[:500]
