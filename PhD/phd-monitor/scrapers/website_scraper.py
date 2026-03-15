"""
Website Scraper — fetches professor homepages and lab pages.
Uses httpx for static pages and Playwright as fallback for JS-rendered pages.
Checks main page + common sub-pages (/openings, /students, /prospective, /join).
"""
import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, Finding

logger = logging.getLogger(__name__)

# Sub-paths to probe automatically for each professor
EXTRA_PATHS = ["/openings", "/students", "/prospective", "/join",
               "/phd-students", "/positions", "/opportunities"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PhDMonitorBot/1.0; "
        "+https://github.com/Rahul-Verma97/PHD)"
    )
}

TIMEOUT = 15  # seconds


class WebsiteScraper(BaseScraper):
    async def scrape(self, professor: dict) -> list[Finding]:
        findings = []
        urls_to_check = self._build_url_list(professor)

        async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT,
                                     follow_redirects=True) as client:
            for url in urls_to_check:
                try:
                    text = await self._fetch(client, url)
                    if text:
                        findings.append(self._make_finding(
                            professor, "website", url, text[:500], text
                        ))
                    await asyncio.sleep(1)  # be polite
                except Exception as e:
                    logger.debug("Website scrape failed for %s (%s): %s",
                                 professor["name"], url, e)

        return findings

    # ── Internals ──────────────────────────────────────────────────────────────

    def _build_url_list(self, professor: dict) -> list[str]:
        urls = []
        base = professor.get("website", "").rstrip("/")
        lab  = professor.get("lab_page", "").rstrip("/")

        if base:
            urls.append(base)
            for path in EXTRA_PATHS:
                urls.append(base + path)

        if lab and lab != base:
            urls.append(lab)
            for path in EXTRA_PATHS:
                urls.append(lab + path)

        return urls

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            text = self._extract_text(resp.text)

            # If page looks JS-rendered (very little text), try Playwright
            if len(text.strip()) < 200:
                text = await self._playwright_fetch(url)

            return text
        except (httpx.HTTPStatusError, httpx.RequestError):
            return None

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        # Remove script, style, nav noise
        for tag in soup(["script", "style", "nav", "footer", "head"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())

    @staticmethod
    async def _playwright_fetch(url: str) -> str:
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=20000)
                content = await page.inner_text("body")
                await browser.close()
                return " ".join(content.split())
        except Exception as e:
            logger.debug("Playwright fallback failed for %s: %s", url, e)
            return ""
