"""
Base scraper — shared dataclass and abstract interface.
All scrapers return a list of Finding objects.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Finding:
    professor_id:   str
    professor_name: str
    university:     str
    source:         str           # 'website', 'twitter', 'rss'
    url:            str
    text_snippet:   str           # relevant excerpt, max 500 chars
    found_at:       datetime = field(default_factory=datetime.utcnow)
    confidence:     str = "none"  # set by Classifier: 'high', 'low', 'none'
    raw_content:    Optional[str] = None


class BaseScraper:
    """Abstract base — every scraper must implement scrape()."""

    async def scrape(self, professor: dict) -> list[Finding]:
        raise NotImplementedError

    @staticmethod
    def _make_finding(professor: dict, source: str, url: str,
                      snippet: str, raw: str = None) -> Finding:
        return Finding(
            professor_id   = professor["id"],
            professor_name = professor["name"],
            university     = professor["university"],
            source         = source,
            url            = url,
            text_snippet   = snippet[:500],
            raw_content    = raw,
        )
