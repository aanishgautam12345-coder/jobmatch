"""We Work Remotely RSS Scraper.

Parses the public RSS feed — no API key needed.
Feed URL: https://weworkremotely.com/remote-jobs.rss

This satisfies the "one scraper sample from a job platform" requirement.
"""

import hashlib
import logging
import feedparser
from app.ingestion.base import JobSource, RawJobRecord, retry_with_backoff

logger = logging.getLogger(__name__)


class WWRScraper(JobSource):
    """Scrapes remote jobs from We Work Remotely RSS feed."""

    FEED_URL = "https://weworkremotely.com/remote-jobs.rss"

    def __init__(self, limit: int = 100):
        self.limit = limit

    @property
    def source_name(self) -> str:
        return "wwr"

    def fetch(self) -> list[RawJobRecord]:
        logger.info("Fetching We Work Remotely RSS feed")

        def _parse_feed():
            return feedparser.parse(self.FEED_URL)

        try:
            feed = retry_with_backoff(_parse_feed, max_retries=3, base_delay=2.0)
        except Exception as e:
            logger.error(f"Failed to fetch WWR feed after retries: {e}")
            return []

        records = []
        for entry in feed.entries[: self.limit]:
            source_id = hashlib.md5(entry.get("link", "").encode()).hexdigest()

            records.append(
                RawJobRecord(
                    source="wwr",
                    source_job_id=source_id,
                    payload={
                        "job_title": entry.get("title", ""),
                        "company": _extract_company(entry.get("title", "")),
                        "job_description": entry.get("summary", ""),
                        "url": entry.get("link", ""),
                        "posted_at": entry.get("published", ""),
                        "category": _extract_tags(entry),
                        "remote": True,
                    },
                )
            )

        logger.info(f"Scraped {len(records)} jobs from We Work Remotely.")
        return records


def _extract_company(title: str) -> str:
    """WWR titles are often 'Company: Job Title'. Extract the company."""
    if ":" in title:
        return title.split(":")[0].strip()
    return ""


def _extract_tags(entry) -> str:
    """Pull category tags if present."""
    tags = entry.get("tags", [])
    if tags:
        return ", ".join(t.get("term", "") for t in tags)
    return ""
