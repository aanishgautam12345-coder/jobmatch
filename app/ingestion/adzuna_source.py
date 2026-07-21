"""Adzuna API Ingestion Source.

Register at developer.adzuna.com to get app_id and app_key.
Free tier: ~25 req/min, 250 req/day. We cache everything in raw_jobs
so we never fetch the same job twice.

Docs: https://developer.adzuna.com/overview
"""

import logging
import httpx
from app.ingestion.base import JobSource, RawJobRecord, retry_with_backoff
from app.config import get_settings

logger = logging.getLogger(__name__)

COUNTRY_CODES = {
    "uk": "gb", "us": "us", "au": "au", "ca": "ca",
    "de": "de", "fr": "fr", "in": "in", "nl": "nl",
}


class AdzunaSource(JobSource):
    """Fetches jobs from the Adzuna API."""

    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(
        self,
        country: str = "gb",
        keywords: str = "",
        results_per_page: int = 50,
        max_pages: int = 3,
    ):
        settings = get_settings()
        self.app_id = settings.adzuna_app_id
        self.app_key = settings.adzuna_app_key
        self.country = COUNTRY_CODES.get(country, country)
        self.keywords = keywords
        self.results_per_page = results_per_page
        self.max_pages = max_pages

        if not self.app_id or not self.app_key:
            raise ValueError(
                "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set in .env"
            )

    @property
    def source_name(self) -> str:
        return "adzuna"

    def fetch(self) -> list[RawJobRecord]:
        records = []

        def _fetch_page(page: int) -> list[dict]:
            url = f"{self.BASE_URL}/{self.country}/search/{page}"
            params = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "results_per_page": self.results_per_page,
                "what": self.keywords,
                "content-type": "application/json",
            }

            logger.info(f"Adzuna: fetching page {page}/{self.max_pages}")
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            return data.get("results", [])

        for page in range(1, self.max_pages + 1):
            try:
                results = retry_with_backoff(
                    lambda p=page: _fetch_page(p),
                    max_retries=3,
                    base_delay=2.0,
                )
            except Exception as e:
                logger.error(f"Adzuna page {page} failed after retries: {e}")
                break

            if not results:
                break

            for job in results:
                records.append(
                    RawJobRecord(
                        source="adzuna",
                        source_job_id=str(job.get("id", "")),
                        payload=_normalise_payload(job),
                    )
                )

            logger.info(f"Adzuna page {page}: got {len(results)} jobs")

        logger.info(f"Fetched {len(records)} jobs from Adzuna ({self.country}).")
        return records


def _normalise_payload(job: dict) -> dict:
    """Map Adzuna's JSON shape to a consistent payload dict."""
    location = job.get("location", {})
    location_parts = location.get("area", [])

    return {
        "job_title": job.get("title", ""),
        "company": job.get("company", {}).get("display_name", ""),
        "job_description": job.get("description", ""),
        "category": job.get("category", {}).get("label", ""),
        "location_display": ", ".join(location_parts) if location_parts else "",
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "contract_type": job.get("contract_type"),
        "contract_time": job.get("contract_time"),
        "url": job.get("redirect_url", ""),
        "posted_at": job.get("created", ""),
    }
