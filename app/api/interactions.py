"""Interaction Tracking API — log user actions on job listings.

Endpoints:
    POST /me/interactions          — log an interaction event
    GET  /me/interactions          — get interaction history
    GET  /me/interactions/summary  — aggregated interaction stats
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.user import User
from app.models.user_interaction import UserInteraction
from app.core.deps import get_current_user

router = APIRouter()

VALID_INTERACTION_TYPES = {
    "impression", "view", "save", "unsave", "dismiss",
    "apply_clicked", "marked_relevant", "marked_irrelevant",
    "notification_opened",
}


class InteractionRequest(BaseModel):
    job_id: str
    interaction_type: str
    source: str | None = None  # search/recommendation/notification
    recommendation_run_id: str | None = None
    metadata: dict | None = None


class InteractionResponse(BaseModel):
    id: str
    job_id: str
    interaction_type: str
    source: str | None
    created_at: datetime


class InteractionSummary(BaseModel):
    total_impressions: int
    total_views: int
    total_saves: int
    total_dismisses: int
    total_applies: int
    ctr: float  # click-through rate (views / impressions)
    save_rate: float  # saves / views


@router.post("/me/interactions", response_model=InteractionResponse)
def log_interaction(
    req: InteractionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Log a user interaction event with a job listing.

    Supports: impression, view, save, unsave, dismiss, apply_clicked,
    marked_relevant, marked_irrelevant, notification_opened.
    """
    if req.interaction_type not in VALID_INTERACTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interaction_type. Must be one of: {sorted(VALID_INTERACTION_TYPES)}",
        )

    interaction = UserInteraction(
        id=uuid.uuid4(),
        user_id=user.id,
        job_id=uuid.UUID(req.job_id),
        interaction_type=req.interaction_type,
        source=req.source,
        recommendation_run_id=(
            uuid.UUID(req.recommendation_run_id) if req.recommendation_run_id else None
        ),
        interaction_metadata=req.metadata,
    )
    db.add(interaction)
    db.commit()

    return InteractionResponse(
        id=str(interaction.id),
        job_id=str(interaction.job_id),
        interaction_type=interaction.interaction_type,
        source=interaction.source,
        created_at=interaction.created_at,
    )


@router.get("/me/interactions")
def get_interactions(
    interaction_type: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's interaction history."""
    query = db.query(UserInteraction).filter(UserInteraction.user_id == user.id)
    if interaction_type:
        query = query.filter(UserInteraction.interaction_type == interaction_type)
    interactions = query.order_by(UserInteraction.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(i.id),
            "job_id": str(i.job_id),
            "interaction_type": i.interaction_type,
            "source": i.source,
            "created_at": i.created_at.isoformat(),
        }
        for i in interactions
    ]


@router.get("/me/interactions/summary", response_model=InteractionSummary)
def get_interaction_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get aggregated interaction statistics for the current user."""
    base = db.query(UserInteraction).filter(UserInteraction.user_id == user.id)

    impressions = base.filter(UserInteraction.interaction_type == "impression").count()
    views = base.filter(UserInteraction.interaction_type == "view").count()
    saves = base.filter(UserInteraction.interaction_type == "save").count()
    dismisses = base.filter(UserInteraction.interaction_type == "dismiss").count()
    applies = base.filter(UserInteraction.interaction_type == "apply_clicked").count()

    ctr = (views / impressions * 100) if impressions > 0 else 0.0
    save_rate = (saves / views * 100) if views > 0 else 0.0

    return InteractionSummary(
        total_impressions=impressions,
        total_views=views,
        total_saves=saves,
        total_dismisses=dismisses,
        total_applies=applies,
        ctr=round(ctr, 1),
        save_rate=round(save_rate, 1),
    )
