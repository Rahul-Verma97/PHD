"""
PhD Professor Hiring Monitor — Main Orchestrator
================================================
Runs all scrapers against every professor in professors.yaml,
classifies results, deduplicates via SQLite, and sends alerts.

Usage:
    python main.py                  # normal run
    DRY_RUN=true python main.py     # test without sending alerts
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from core.classifier    import Classifier
from core.state_manager import StateManager
from core.alert_engine  import AlertEngine
from scrapers.website_scraper import WebsiteScraper
from scrapers.twitter_scraper import TwitterScraper
from scrapers.rss_scraper     import RSSScraper

# ── Bootstrap ────────────────────────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

BASE_DIR  = Path(__file__).parent
CONFIG    = BASE_DIR / "config"
DATA_DIR  = BASE_DIR / "data"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_config():
    with open(CONFIG / "professors.yaml") as f:
        professors = yaml.safe_load(f)["professors"]
    with open(CONFIG / "keywords.yaml") as f:
        keywords = yaml.safe_load(f)
    return professors, keywords


async def scrape_professor(professor: dict, scrapers: list,
                            classifier: Classifier) -> list:
    """Run all scrapers for one professor and return classified new hits."""
    hits = []
    for scraper in scrapers:
        try:
            findings = await scraper.scrape(professor)
            for finding in findings:
                is_hit, confidence = classifier.classify(finding.text_snippet)
                if is_hit:
                    finding.confidence = confidence
                    hits.append(finding)
        except Exception as e:
            logger.warning(
                "Scraper %s failed for %s: %s",
                scraper.__class__.__name__, professor["name"], e,
            )
    return hits


# ── Main ─────────────────────────────────────────────────────────────────────

async def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    professors, keywords = load_config()
    max_profs = int(os.getenv("MAX_PROFESSORS_PER_RUN", len(professors)))
    professors = professors[:max_profs]

    logger.info("Starting PhD Monitor — %d professors to check", len(professors))

    state    = StateManager(str(DATA_DIR / "state.db"))
    classify = Classifier(keywords)
    alerter  = AlertEngine()
    scrapers = [WebsiteScraper(), TwitterScraper(), RSSScraper()]

    all_raw     = 0
    all_new     = []
    all_errors  = []

    # Process professors in batches of 10 to avoid hammering servers
    BATCH = 10
    for i in range(0, len(professors), BATCH):
        batch = professors[i : i + BATCH]
        tasks = [scrape_professor(p, scrapers, classify) for p in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for prof, result in zip(batch, results):
            if isinstance(result, Exception):
                msg = f"{prof['name']}: {result}"
                logger.error(msg)
                all_errors.append(msg)
                continue

            all_raw += len(result)
            for finding in result:
                if state.is_new(finding):
                    state.record(finding)
                    all_new.append(finding)
                    logger.info(
                        "NEW HIT [%s] %s — %s — %s",
                        finding.confidence.upper(),
                        finding.professor_name,
                        finding.source,
                        finding.url,
                    )

        logger.info(
            "Batch %d/%d done  (running new total: %d)",
            min(i + BATCH, len(professors)), len(professors), len(all_new),
        )
        await asyncio.sleep(2)  # brief pause between batches

    # Send consolidated alert
    if all_new:
        logger.info("Sending alert for %d new finding(s)…", len(all_new))
        alerter.send(all_new)
    else:
        logger.info("No new hiring signals found in this run.")

    state.log_run(
        professors_checked = len(professors),
        findings_raw       = all_raw,
        findings_new       = len(all_new),
        errors             = all_errors,
    )

    logger.info(
        "Run complete — checked=%d  raw_hits=%d  new_alerts=%d  errors=%d",
        len(professors), all_raw, len(all_new), len(all_errors),
    )


if __name__ == "__main__":
    asyncio.run(run())
