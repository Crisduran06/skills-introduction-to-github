from __future__ import annotations
from datetime import date
from typing import Optional
from rapidfuzz import fuzz
from sqlalchemy.orm import Session
from app.models import Project
from app.schemas import ProjectIn


SIMILARITY_THRESHOLD = 88


def _normalize(s: str) -> str:
    return s.lower().strip()


def find_duplicate(db: Session, incoming: ProjectIn) -> Optional[Project]:
    candidates = db.query(Project).filter(
        Project.agency_owner == incoming.agency_owner,
    ).all()

    if not candidates and incoming.location_city:
        candidates = db.query(Project).filter(
            Project.location_city == incoming.location_city,
        ).all()

    for existing in candidates:
        name_sim = fuzz.token_sort_ratio(
            _normalize(existing.project_name),
            _normalize(incoming.project_name),
        )

        date_match = (
            existing.bid_due_date == incoming.bid_due_date
            if incoming.bid_due_date
            else True
        )

        if name_sim >= SIMILARITY_THRESHOLD and date_match:
            return existing

    return None


def merge_project(existing: Project, incoming: ProjectIn) -> Project:
    """Merge incoming data into existing record without overwriting better data."""
    if not existing.description and incoming.description:
        existing.description = incoming.description
    if not existing.trade_scope_raw and incoming.trade_scope_raw:
        existing.trade_scope_raw = incoming.trade_scope_raw
    if not existing.estimate_value and incoming.estimate_value:
        existing.estimate_value = incoming.estimate_value
    if not existing.engineer_estimate and incoming.engineer_estimate:
        existing.engineer_estimate = incoming.engineer_estimate
    if not existing.bid_due_date and incoming.bid_due_date:
        existing.bid_due_date = incoming.bid_due_date
    if not existing.prebid_date and incoming.prebid_date:
        existing.prebid_date = incoming.prebid_date
    if not existing.location_city and incoming.location_city:
        existing.location_city = incoming.location_city
    if not existing.location_county and incoming.location_county:
        existing.location_county = incoming.location_county
    if not existing.documents_url and incoming.documents_url:
        existing.documents_url = incoming.documents_url
    if not existing.planholders_url and incoming.planholders_url:
        existing.planholders_url = incoming.planholders_url
    if not existing.results_url and incoming.results_url:
        existing.results_url = incoming.results_url
    if not existing.award_url and incoming.award_url:
        existing.award_url = incoming.award_url
    if not existing.archive_url and incoming.archive_url:
        existing.archive_url = incoming.archive_url

    if incoming.source_url and incoming.source_url not in (existing.source_url or ""):
        if existing.source_url:
            existing.source_url = f"{existing.source_url} | {incoming.source_url}"
        else:
            existing.source_url = incoming.source_url

    # Always allow progression: open → awarded/archived
    if incoming.is_archived and not existing.is_archived:
        existing.is_archived = True
    if incoming.status in ("awarded", "bid_opened") and existing.status == "open":
        existing.status = incoming.status

    return existing


def normalize_company_name(name: str) -> str:
    name = name.lower().strip()
    for suffix in [", inc.", " inc.", ", llc", " llc", ", corp.", " corp.",
                   ", ltd.", " ltd.", ", co.", " co.", " company", " construction"]:
        name = name.replace(suffix, "")
    return name.strip()
