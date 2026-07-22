from app.models.user import User, UserProfile, NotificationPreference
from app.models.job import RawJob, Job, JobSkill
from app.models.job_posting import JobPosting
from app.models.recommendation import Recommendation, SavedJob
from app.models.recommendation_run import RecommendationRun
from app.models.notification import Notification
from app.models.ingestion_run import IngestionRun
from app.models.processing_error import ProcessingError
from app.models.user_interaction import UserInteraction
from app.models.token_blacklist import TokenBlacklist
from app.models.normalization_alias import NormalizationAlias

__all__ = [
    "User", "UserProfile", "NotificationPreference",
    "RawJob", "Job", "JobSkill",
    "JobPosting",
    "Recommendation", "SavedJob",
    "RecommendationRun",
    "Notification",
    "IngestionRun",
    "ProcessingError",
    "UserInteraction",
    "TokenBlacklist",
    "NormalizationAlias",
]
