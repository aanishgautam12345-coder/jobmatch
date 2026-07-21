"""Reed.co.uk API Ingestion Source.

Fetches jobs from the Reed.co.uk job search API.
Free tier: requires registration at api.reed.co.uk.
Docs: https://api.reed.co.uk/docs/search
"""

import logging
import time
import httpx
from app.ingestion.base import JobSource, RawJobRecord, retry_with_backoff
from app.config import get_settings

logger = logging.getLogger(__name__)


class ReedSource(JobSource):
    """Fetches jobs from the Reed.co.uk API."""

    BASE_URL = "https://www.reed.co.uk/api/1.0"

    def __init__(
        self,
        keywords: str = "",
        location: str = "",
        distance: int = 10,
        full_time: bool | None = None,
        part_time: bool | None = None,
        permanent: bool | None = None,
        contract: bool | None = None,
        temp: bool | None = None,
        min_salary: int | None = None,
        max_salary: int | None = None,
        results_to_take: int = 100,
        max_pages: int = 5,
    ):
        settings = get_settings()
        self.api_key = settings.reed_api_key
        self.keywords = keywords
        self.location = location
        self.distance = distance
        self.full_time = full_time
        self.part_time = part_time
        self.permanent = permanent
        self.contract = contract
        self.temp = temp
        self.min_salary = min_salary
        self.max_salary = max_salary
        self.results_to_take = min(results_to_take, 100)
        self.max_pages = max_pages

        if not self.api_key:
            raise ValueError("REED_API_KEY must be set in .env")

    @property
    def source_name(self) -> str:
        return "reed"

    def fetch(self) -> list[RawJobRecord]:
        records = []

        with httpx.Client(timeout=30, auth=(self.api_key, "")) as client:
            for page in range(self.max_pages):
                skip = page * self.results_to_take
                params = {
                    "keywords": self.keywords,
                    "resultsToTake": self.results_to_take,
                    "resultsToSkip": skip,
                }

                if self.location:
                    params["locationName"] = self.location
                    params["distanceFromLocation"] = self.distance
                if self.full_time is not None:
                    params["fullTime"] = str(self.full_time).lower()
                if self.part_time is not None:
                    params["partTime"] = str(self.part_time).lower()
                if self.permanent is not None:
                    params["permanent"] = str(self.permanent).lower()
                if self.contract is not None:
                    params["contract"] = str(self.contract).lower()
                if self.temp is not None:
                    params["temp"] = str(self.temp).lower()
                if self.min_salary is not None:
                    params["minimumSalary"] = self.min_salary
                if self.max_salary is not None:
                    params["maximumSalary"] = self.max_salary

                try:
                    def _fetch():
                        logger.info(f"Reed: fetching page {page + 1}/{self.max_pages}")
                        resp = client.get(f"{self.BASE_URL}/search", params=params)
                        resp.raise_for_status()
                        return resp.json()

                    data = retry_with_backoff(_fetch, max_retries=3, base_delay=1.0)
                except Exception as e:
                    logger.error(f"Reed page {page + 1} failed after retries: {e}")
                    break

                results = data.get("results", [])
                if not results:
                    break

                for job in results:
                    job_id = str(job.get("jobId", ""))
                    if not job_id:
                        continue

                    try:
                        detail = retry_with_backoff(
                            lambda jid=job_id: _fetch_job_detail(client, self.BASE_URL, jid, self.api_key),
                            max_retries=2,
                            base_delay=0.5,
                        )
                    except Exception:
                        detail = None

                    records.append(
                        RawJobRecord(
                            source="reed",
                            source_job_id=job_id,
                            payload=_normalise_payload(job, detail),
                        )
                    )

                logger.info(f"Reed page {page + 1}: got {len(results)} jobs")

                if page < self.max_pages - 1:
                    time.sleep(0.5)

        logger.info(f"Fetched {len(records)} jobs from Reed.co.uk.")
        return records


def _fetch_job_detail(
    client: httpx.Client, base_url: str, job_id: str, api_key: str
) -> dict | None:
    """Fetch full job details from the Reed API."""
    try:
        resp = client.get(f"{base_url}/jobs/{job_id}", auth=(api_key, ""))
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _normalise_payload(job: dict, detail: dict | None) -> dict:
    """Map Reed's JSON shape to a consistent payload dict."""
    source = detail if detail else job

    location = source.get("locationName", "")
    salary_min = source.get("yearlyMinimumSalary") or source.get("minimumSalary")
    salary_max = source.get("yearlyMaximumSalary") or source.get("maximumSalary")
    currency = source.get("currency", "GBP")
    salary_type = source.get("salaryType", "")
    contract_type = source.get("contractType", "")
    job_type = source.get("jobType", "")
    url = source.get("externalUrl") or source.get("url", "")

    return {
        "job_title": source.get("jobTitle", ""),
        "company": source.get("employerName", ""),
        "job_description": source.get("jobDescription", ""),
        "location_display": location,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": currency,
        "salary_type": salary_type,
        "contract_type": contract_type,
        "contract_time": job_type,
        "url": url,
        "posted_at": "",
        "employer_id": str(source.get("employerId", "")),
    }
