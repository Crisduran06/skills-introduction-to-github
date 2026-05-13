"""Google Sheets export module. Credentials are optional — app starts without them."""
from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session
from app.models import (
    Project, Source, Company, Planholder,
    BidResult, ProjectBidAnalytics, CompanyProjectParticipation,
)
from app.config import settings


def _sheets_available() -> bool:
    try:
        import gspread  # noqa: F401
        import google.auth  # noqa: F401
        return bool(settings.google_sheets_credentials_file and settings.google_sheets_spreadsheet_id)
    except ImportError:
        return False


def _get_client():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(settings.google_sheets_credentials_file, scopes=scopes)
    return gspread.authorize(creds)


def format_project_row(p: Project) -> list[Any]:
    return [
        p.id,
        p.project_name,
        p.agency_owner or "",
        p.location_city or "",
        str(p.bid_due_date) if p.bid_due_date else "",
        p.status,
        p.relevance_score or "",
        p.estimate_value or "",
        p.source_url or "",
        str(p.created_at.date()) if p.created_at else "",
    ]


def format_bid_result_row(r: BidResult) -> list[Any]:
    return [
        r.id,
        r.project_id,
        r.company_id or "",
        r.bid_amount or "",
        r.bid_rank or "",
        "Yes" if r.is_low_bidder else "No",
        "Yes" if r.is_awarded else "No",
        r.delta_from_low_amount or "",
        r.delta_from_low_percent or "",
        r.delta_from_engineer_estimate_percent or "",
    ]


def sync_to_sheets(db: Session) -> dict:
    if not _sheets_available():
        return {"status": "skipped", "reason": "Google Sheets not configured"}

    try:
        client = _get_client()
        spreadsheet = client.open_by_key(settings.google_sheets_spreadsheet_id)

        projects = db.query(Project).all()
        _write_sheet(spreadsheet, "Projects", [
            ["ID", "Name", "Agency", "City", "Bid Due", "Status", "Score", "Estimate", "URL", "Created"],
            *[format_project_row(p) for p in projects],
        ])

        results = db.query(BidResult).all()
        _write_sheet(spreadsheet, "BidResults", [
            ["ID", "ProjectID", "CompanyID", "BidAmount", "Rank", "LowBidder", "Awarded",
             "DeltaFromLow$", "DeltaFromLow%", "DeltaFromEE%"],
            *[format_bid_result_row(r) for r in results],
        ])

        return {"status": "success", "projects_synced": len(projects), "results_synced": len(results)}

    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


def _write_sheet(spreadsheet, sheet_name: str, rows: list[list]) -> None:
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except Exception:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=26)
    ws.clear()
    if rows:
        ws.update("A1", rows)
