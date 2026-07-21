"""Users API â€” profile management for authenticated users."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserProfile, NotificationPreference
from app.core.deps import get_current_user
from app.services.embedding import build_profile_text, generate_embedding

router = APIRouter()


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    skills: list[str] | None = None
    experience_years: int | None = None
    experience_level: str | None = None
    preferred_locations: list[str] | None = None
    preferred_job_types: list[str] | None = None
    min_salary: float | None = None
    salary_currency: str | None = None
    career_interests: str | None = None


class NotificationPrefUpdate(BaseModel):
    email_enabled: bool | None = None
    min_match_score: float | None = None
    frequency: str | None = None


class ProfileResponse(BaseModel):
    full_name: str | None
    headline: str | None
    skills: list[str] | None
    experience_years: int | None
    experience_level: str | None
    preferred_locations: list[str] | None
    preferred_job_types: list[str] | None
    min_salary: float | None
    salary_currency: str | None
    career_interests: str | None
    has_embedding: bool

    class Config:
        from_attributes = True


@router.get("/me/profile", response_model=ProfileResponse)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the current user's profile."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return ProfileResponse(
        full_name=profile.full_name,
        headline=profile.headline,
        skills=profile.skills,
        experience_years=profile.experience_years,
        experience_level=profile.experience_level,
        preferred_locations=profile.preferred_locations,
        preferred_job_types=profile.preferred_job_types,
        min_salary=profile.min_salary,
        salary_currency=profile.salary_currency,
        career_interests=profile.career_interests,
        has_embedding=profile.profile_embedding is not None,
    )


@router.put("/me/profile", response_model=ProfileResponse)
def update_profile(
    update: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's profile. Recomputes the profile embedding."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Update fields that were provided
    for field, value in update.dict(exclude_unset=True).items():
        setattr(profile, field, value)

    # Recompute embedding
    text = build_profile_text(
        headline=profile.headline,
        skills=profile.skills,
        career_interests=profile.career_interests,
        experience_level=profile.experience_level,
    )
    profile.profile_embedding = generate_embedding(text, is_query=True)

    db.commit()
    db.refresh(profile)

    return ProfileResponse(
        full_name=profile.full_name,
        headline=profile.headline,
        skills=profile.skills,
        experience_years=profile.experience_years,
        experience_level=profile.experience_level,
        preferred_locations=profile.preferred_locations,
        preferred_job_types=profile.preferred_job_types,
        min_salary=profile.min_salary,
        salary_currency=profile.salary_currency,
        career_interests=profile.career_interests,
        has_embedding=profile.profile_embedding is not None,
    )


@router.put("/me/notifications")
def update_notification_prefs(
    update: NotificationPrefUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update notification preferences."""
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user.id
    ).first()
    if not prefs:
        raise HTTPException(status_code=404, detail="Notification preferences not found")

    for field, value in update.dict(exclude_unset=True).items():
        setattr(prefs, field, value)

    db.commit()
    return {"message": "Notification preferences updated"}
