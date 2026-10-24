import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.cache import bump_version, cache_get, cache_set, make_key
from app.database import get_db
from app.deps import get_current_user, require_admin
from app.enums import ALLOWED_TRANSITIONS, LeadStatus, Role
from app.models import Lead, User
from app.schemas import (
    LeadCreate,
    LeadOut,
    LeadPage,
    LeadStats,
    LeadStatusUpdate,
    LeadUpdate,
)

router = APIRouter(prefix="/leads", tags=["leads"])

SORT_COLUMNS = {
    "created_at": Lead.created_at.asc(),
    "-created_at": Lead.created_at.desc(),
    "name": Lead.name.asc(),
    "-name": Lead.name.desc(),
}


def _is_admin(user: User) -> bool:
    return user.role == Role.ADMIN.value


def _scope(user: User) -> str:
    """Cache scope: admins share one view, each agent has their own."""
    return "all" if _is_admin(user) else f"u{user.id}"


def _get_lead_or_404(db: Session, lead_id: int, user: User) -> Lead:
    lead = db.get(Lead, lead_id)
    # Agents get 404 (not 403) for other people's leads so ids can't be probed.
    if lead is None or (not _is_admin(user) and lead.owner_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


def _check_owner(db: Session, owner_id: int, user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can assign owners")
    if db.get(User, owner_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Owner not found")


@router.get("", response_model=LeadPage)
def list_leads(
    response: Response,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_filter: LeadStatus | None = Query(None, alias="status"),
    source: str | None = None,
    q: str | None = Query(None, description="Search name, email or company"),
    sort: Literal["created_at", "-created_at", "name", "-name"] = "-created_at",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    key = make_key("leads:list", _scope(user), page, size, status_filter, source, q, sort)
    cached = cache_get(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    response.headers["X-Cache"] = "MISS"

    stmt = select(Lead)
    if not _is_admin(user):
        stmt = stmt.where(Lead.owner_id == user.id)
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter.value)
    if source:
        stmt = stmt.where(Lead.source == source)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Lead.name.ilike(like), Lead.email.ilike(like), Lead.company.ilike(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SORT_COLUMNS[sort], Lead.id).offset((page - 1) * size).limit(size)
    ).all()
    result = LeadPage(
        items=[LeadOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total else 0,
    ).model_dump(mode="json")
    cache_set(key, result)
    return result


@router.get("/stats/summary", response_model=LeadStats)
def lead_stats(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lead counts per pipeline status (cached)."""
    key = make_key("leads:stats", _scope(user))
    cached = cache_get(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    response.headers["X-Cache"] = "MISS"

    stmt = select(Lead.status, func.count()).group_by(Lead.status)
    if not _is_admin(user):
        stmt = stmt.where(Lead.owner_id == user.id)
    counts = {s.value: 0 for s in LeadStatus}
    counts.update({status_: n for status_, n in db.execute(stmt).all()})
    result = {"total": sum(counts.values()), "by_status": counts}
    cache_set(key, result)
    return result


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    owner_id = user.id
    if payload.owner_id is not None:
        _check_owner(db, payload.owner_id, user)
        owner_id = payload.owner_id
    lead = Lead(
        name=payload.name,
        email=payload.email.lower(),
        phone=payload.phone,
        company=payload.company,
        source=payload.source,
        status=LeadStatus.NEW.value,
        owner_id=owner_id,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    bump_version()
    return lead


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get_lead_or_404(db, lead_id, user)


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lead = _get_lead_or_404(db, lead_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        if changes["owner_id"] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "owner_id cannot be null")
        _check_owner(db, changes["owner_id"], user)
    if "email" in changes and changes["email"]:
        changes["email"] = changes["email"].lower()
    for field, value in changes.items():
        setattr(lead, field, value)
    db.commit()
    db.refresh(lead)
    bump_version()
    return lead


@router.patch("/{lead_id}/status", response_model=LeadOut)
def update_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move a lead through the pipeline: new -> contacted -> won/lost (won/lost are final)."""
    lead = _get_lead_or_404(db, lead_id, user)
    current = LeadStatus(lead.status)
    if payload.status not in ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot move a lead from '{current.value}' to '{payload.status.value}'",
        )
    lead.status = payload.status.value
    db.commit()
    db.refresh(lead)
    bump_version()
    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    db.delete(lead)
    db.commit()
    bump_version()
