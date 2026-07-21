from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class RawJobRecord:
    """Standard shape every source must produce before storage."""
    source: str               # "csv" / "adzuna" / "wwr"
    source_job_id: str         # Unique ID from the source
    payload: dict[str, Any]    # The entire raw record as a dict


class JobSource(ABC):
    """Abstract base for all job data sources."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this source (e.g. 'csv', 'adzuna', 'wwr')."""
        ...

    @abstractmethod
    def fetch(self) -> list[RawJobRecord]:
        """Fetch raw job records from this source."""
        ...


def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
):
    """Execute func with exponential backoff retry logic.

    Args:
        func: Callable to execute.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay between retries.
        backoff_factor: Multiplier for exponential backoff.
        retryable_exceptions: Tuple of exceptions that trigger retry.

    Returns:
        Result of func call.

    Raises:
        Last exception after all retries exhausted.
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} attempts failed: {e}")

    raise last_exception
