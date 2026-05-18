from __future__ import annotations
import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, init_db
from app.models import Source, Project, ProjectBidAnalytics, BidResult, Planholder, Addendum, ProjectNote, DecisionStatus, ProjectSubcontractor
from app.schemas import ManualImportIn
from app.tasks import (
    seed_sources, seed_fixtures, fetch_all_sources, fetch_all_archives,
    fetch_source, export_csv,
)
from app.analytics import calculate_all_analytics, get_trend_analytics
from app.connectors.manual_import import parse_project_text
from app.connectors.base import StubConnector


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db_gen = get_db()
    db = next(db_gen)
    try:
        seed_sources(db)
        if settings.autofetch_live:
            from app.models import Project
            from datetime import datetime, timezone
            last = db.query(Source.last_checked_at).filter(
                Source.status == "live"
            ).order_by(Source.last_checked_at.desc()).first()
            last_ts = last[0] if last and last[0] else None
            stale = (
                last_ts is None
                or (datetime.now(timezone.utc) - last_ts.replace(tzinfo=timezone.utc)).total_seconds() > 3600
            )
            if stale:
                fetch_all_sources(db, fixture=False)
                calculate_all_analytics(db)
        elif settings.autoseed_fixtures:
            from app.models import Project
            if db.query(Project).count() == 0:
                seed_fixtures(db)
    finally:
        db.close()

    if settings.scheduler_enabled:
        from app.scheduler import start_scheduler
        start_scheduler()

    yield

    if settings.scheduler_enabled:
        from app.scheduler import stop_scheduler
        stop_scheduler()


app = FastAPI(title="Bid Intel", lifespan=lifespan)

templates = Jinja2Templates(directory=str(settings.templates_dir))


def _fmt_currency(val) -> str:
    if val is None:
        return "—"
    return f"${val:,.0f}"


def _fmt_pct(val) -> str:
    if val is None:
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"


templates.env.filters["currency"] = _fmt_currency
templates.env.filters["pct"] = _fmt_pct
templates.env.globals["enumerate"] = enumerate


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    filter: Optional[str] = None,
    bid_type: Optional[str] = None,
    project_type: Optional[str] = None,
    agency: Optional[str] = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    week_out = today + timedelta(days=7)

    total_open = db.query(Project).filter(Project.status == "open", Project.is_archived == False).count()  # noqa: E712
    due_this_week = db.query(Project).filter(
        Project.bid_due_date >= today,
        Project.bid_due_date <= week_out,
        Project.is_archived == False,  # noqa: E712
    ).count()
    high_relevance = db.query(Project).filter(
        Project.relevance_score >= 4,
        Project.is_archived == False,  # noqa: E712
    ).count()

    results_this_week = db.query(BidResult).filter(
        BidResult.result_date >= today - timedelta(days=7),
    ).count()

    q = db.query(Project)
    filter_label = None

    if filter == "open":
        q = q.filter(Project.status == "open", Project.is_archived == False)  # noqa: E712
        filter_label = "Open Bids"
    elif filter == "due_this_week":
        q = q.filter(
            Project.bid_due_date >= today,
            Project.bid_due_date <= week_out,
            Project.is_archived == False,  # noqa: E712
        )
        filter_label = "Due This Week"
    elif filter == "high_relevance":
        q = q.filter(Project.relevance_score >= 4, Project.is_archived == False)  # noqa: E712
        filter_label = "High Relevance (4–5)"
    elif filter == "results_this_week":
        result_project_ids = [
            r.project_id for r in db.query(BidResult.project_id)
            .filter(BidResult.result_date >= today - timedelta(days=7))
            .distinct()
        ]
        q = q.filter(Project.id.in_(result_project_ids))
        filter_label = "Results This Week"
    else:
        q = q.filter(Project.is_archived == False)  # noqa: E712

    if bid_type:
        q = q.filter(Project.bid_type == bid_type)
    if project_type:
        q = q.filter(Project.project_type == project_type)
    if agency:
        q = q.filter(Project.agency_owner == agency)

    projects = (
        q.order_by(Project.bid_due_date.asc().nulls_last(), Project.relevance_score.desc().nulls_last())
        .limit(200)
        .all()
    )

    # Build filter option lists from live projects
    bid_types = [r[0] for r in db.query(Project.bid_type).filter(
        Project.is_archived == False, Project.bid_type.isnot(None)  # noqa: E712
    ).distinct().order_by(Project.bid_type).all()]
    project_types = [r[0] for r in db.query(Project.project_type).filter(
        Project.is_archived == False, Project.project_type.isnot(None)  # noqa: E712
    ).distinct().order_by(Project.project_type).all()]
    agencies = [r[0] for r in db.query(Project.agency_owner).filter(
        Project.is_archived == False, Project.agency_owner.isnot(None)  # noqa: E712
    ).distinct().order_by(Project.agency_owner).all()]

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_open": total_open,
        "due_this_week": due_this_week,
        "high_relevance": high_relevance,
        "results_this_week": results_this_week,
        "projects": projects,
        "today": today,
        "week_out": week_out,
        "active_filter": filter,
        "filter_label": filter_label,
        "bid_types": bid_types,
        "project_types": project_types,
        "agencies": agencies,
        "selected_bid_type": bid_type,
        "selected_project_type": project_type,
        "selected_agency": agency,
    })


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    bid_results = (
        db.query(BidResult)
        .filter_by(project_id=project_id)
        .order_by(BidResult.bid_rank.asc().nulls_last())
        .all()
    )
    planholders = db.query(Planholder).filter_by(project_id=project_id).all()
    subcontractors = (
        db.query(ProjectSubcontractor)
        .filter_by(project_id=project_id)
        .order_by(ProjectSubcontractor.trade_scope.asc().nulls_last())
        .all()
    )
    addenda = db.query(Addendum).filter_by(project_id=project_id).order_by(Addendum.addendum_number).all()
    notes = db.query(ProjectNote).filter_by(project_id=project_id).order_by(ProjectNote.created_at.desc()).all()
    analytics = db.query(ProjectBidAnalytics).filter_by(project_id=project_id).first()
    decision = db.query(DecisionStatus).filter_by(project_id=project_id).first()

    from app.models import Company
    company_map: dict[int, str] = {}
    for r in bid_results:
        if r.company_id and r.company_id not in company_map:
            c = db.query(Company).filter_by(id=r.company_id).first()
            if c:
                company_map[r.company_id] = c.name
    for ph in planholders:
        if ph.company_id and ph.company_id not in company_map:
            c = db.query(Company).filter_by(id=ph.company_id).first()
            if c:
                company_map[ph.company_id] = c.name
    for s in subcontractors:
        if s.company_id and s.company_id not in company_map:
            c = db.query(Company).filter_by(id=s.company_id).first()
            if c:
                company_map[s.company_id] = c.name

    return templates.TemplateResponse(request, "project_detail.html", {
        "project": project,
        "bid_results": bid_results,
        "planholders": planholders,
        "subcontractors": subcontractors,
        "addenda": addenda,
        "notes": notes,
        "analytics": analytics,
        "decision": decision,
        "company_map": company_map,
    })


@app.get("/archive", response_class=HTMLResponse)
async def archive_page(
    request: Request,
    agency: Optional[str] = None,
    year: Optional[int] = None,
    bid_type: Optional[str] = None,
    project_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy import extract
    q = db.query(Project).filter(
        (Project.is_archived == True) | (Project.status.in_(["awarded", "bid_opened"]))  # noqa: E712
    )
    if agency:
        q = q.filter(Project.agency_owner == agency)
    if year:
        q = q.filter(extract("year", Project.bid_due_date) == year)
    if bid_type:
        q = q.filter(Project.bid_type == bid_type)
    if project_type:
        q = q.filter(Project.project_type == project_type)

    projects = q.order_by(Project.bid_due_date.desc().nulls_last()).limit(500).all()

    analytics_map: dict[int, ProjectBidAnalytics] = {}
    if projects:
        for a in db.query(ProjectBidAnalytics).filter(
            ProjectBidAnalytics.project_id.in_([p.id for p in projects])
        ).all():
            analytics_map[a.project_id] = a

    agencies = [r[0] for r in db.query(Project.agency_owner).filter(
        (Project.is_archived == True) | (Project.status.in_(["awarded", "bid_opened"])),  # noqa: E712
        Project.agency_owner.isnot(None),
    ).distinct().order_by(Project.agency_owner).all()]

    years = sorted({
        p.bid_due_date.year for p in
        db.query(Project).filter(
            (Project.is_archived == True) | (Project.status.in_(["awarded", "bid_opened"])),  # noqa: E712
            Project.bid_due_date.isnot(None),
        ).all()
    }, reverse=True)

    archive_bid_types = [r[0] for r in db.query(Project.bid_type).filter(
        (Project.is_archived == True) | (Project.status.in_(["awarded", "bid_opened"])),  # noqa: E712
        Project.bid_type.isnot(None),
    ).distinct().order_by(Project.bid_type).all()]
    archive_project_types = [r[0] for r in db.query(Project.project_type).filter(
        (Project.is_archived == True) | (Project.status.in_(["awarded", "bid_opened"])),  # noqa: E712
        Project.project_type.isnot(None),
    ).distinct().order_by(Project.project_type).all()]

    total = len(projects)
    return templates.TemplateResponse(request, "archive.html", {
        "projects": projects,
        "analytics_map": analytics_map,
        "agencies": agencies,
        "years": years,
        "selected_agency": agency,
        "selected_year": year,
        "bid_types": archive_bid_types,
        "project_types": archive_project_types,
        "selected_bid_type": bid_type,
        "selected_project_type": project_type,
        "total": total,
    })


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, db: Session = Depends(get_db)):
    trends = get_trend_analytics(db)
    total_projects = db.query(Project).count()
    total_bid_results = db.query(BidResult).count()
    return templates.TemplateResponse(request, "analytics.html", {
        "trends": trends,
        "total_projects": total_projects,
        "total_bid_results": total_bid_results,
    })


@app.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request, db: Session = Depends(get_db)):
    sources = db.query(Source).order_by(Source.name).all()
    return templates.TemplateResponse(request, "sources.html", {"sources": sources})


@app.get("/manual-import", response_class=HTMLResponse)
async def manual_import_page(request: Request):
    return templates.TemplateResponse(request, "manual_import.html", {})


@app.get("/share/{project_id}", response_class=HTMLResponse)
async def share_project(request: Request, project_id: int, db: Session = Depends(get_db)):
    import re
    project = db.query(Project).filter_by(id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    planholders = db.query(Planholder).filter_by(project_id=project_id).all()
    analytics = db.query(ProjectBidAnalytics).filter_by(project_id=project_id).first()

    from app.models import Company
    gc_names: list[str] = []
    for ph in planholders:
        name = None
        if ph.company_id:
            c = db.query(Company).filter_by(id=ph.company_id).first()
            if c:
                name = c.name
        if not name:
            name = ph.listed_as
        if name:
            gc_names.append(name)

    # Extract square footage from description or trade_scope_raw
    sq_ft = None
    for text in [project.description, project.trade_scope_raw]:
        if text:
            m = re.search(r'(\d[\d,]*)\s*(?:sq\.?\s*ft\.?|square\s*feet)', text, re.I)
            if m:
                sq_ft = m.group(1).replace(",", "")
                break

    days_left = None
    if project.bid_due_date:
        days_left = (project.bid_due_date - date.today()).days

    return templates.TemplateResponse(request, "share.html", {
        "project": project,
        "gc_names": gc_names,
        "sq_ft": sq_ft,
        "analytics": analytics,
        "days_left": days_left,
    })


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/seed-fixtures")
async def api_seed_fixtures(db: Session = Depends(get_db)):
    result = seed_fixtures(db)
    return result


@app.post("/api/fetch-all")
async def api_fetch_all(db: Session = Depends(get_db)):
    results = fetch_all_sources(db, fixture=False)
    return {"results": results}


@app.post("/api/fetch-archives")
async def api_fetch_archives(db: Session = Depends(get_db)):
    results = fetch_all_archives(db, fixture=False)
    calculated = calculate_all_analytics(db)
    return {"results": results, "analytics_calculated": calculated}


@app.post("/api/calculate-analytics")
async def api_calculate_analytics(db: Session = Depends(get_db)):
    count = calculate_all_analytics(db)
    return {"projects_calculated": count}


@app.get("/api/debug-archives")
async def api_debug_archives():
    from app.tasks import get_connector
    report = {}
    for key in ["bart", "mountain_view", "vta", "ebmud", "sfpuc", "sf_public_works"]:
        try:
            connector = get_connector(key, fixture=False)
            if connector is None:
                report[key] = {"error": "no connector"}
                continue
            if hasattr(connector, "fetch_archived_with_results"):
                pairs = connector.fetch_archived_with_results()
                report[key] = {
                    "count": len(pairs),
                    "with_bid_results": sum(1 for _, r in pairs if r),
                    "sample": pairs[0][0].project_name if pairs else None,
                }
            elif hasattr(connector, "fetch_archived_projects"):
                projects = connector.fetch_archived_projects()
                report[key] = {
                    "count": len(projects),
                    "sample": projects[0].project_name if projects else None,
                }
            else:
                report[key] = {"error": "no archive method"}
        except Exception as exc:
            report[key] = {"error": str(exc)}
    return report


@app.get("/api/debug-source/{key}")
async def api_debug_source(key: str, db: Session = Depends(get_db)):
    from app.tasks import get_connector
    connector = get_connector(key)
    if connector is None:
        source = db.query(Source).filter_by(key=key).first()
        if source:
            return {
                "key": key,
                "name": source.name,
                "status": source.status,
                "platform_type": source.platform_type,
                "notes": source.notes,
                "connector": "stub — not yet implemented",
            }
        raise HTTPException(status_code=404, detail=f"Source '{key}' not found")
    return connector.debug_source()


@app.post("/api/import-pdf-url")
async def api_import_pdf_url(
    request: Request, db: Session = Depends(get_db)
):
    from app.tasks import upsert_project, save_bid_results, seed_sources
    from app.connectors.pdf_extractor import extract_pdf_text, parse_award_pdf
    from app.analytics import calculate_bid_deltas, calculate_project_analytics
    body = await request.json()
    pdf_url = (body.get("pdf_url") or "").strip()
    agency = (body.get("agency") or "Unknown Agency").strip()
    city = (body.get("city") or "").strip()
    county = (body.get("county") or "").strip()
    if not pdf_url:
        return JSONResponse({"error": "pdf_url is required"}, status_code=400)

    text = extract_pdf_text(pdf_url)
    if not text:
        return JSONResponse({"error": "Could not extract text from PDF — may be image-only or inaccessible"}, status_code=422)

    project_in, bid_results_in = parse_award_pdf(text, pdf_url, agency, city, county)
    if not project_in:
        return JSONResponse({"error": "Could not find a project title in the PDF"}, status_code=422)

    seed_sources(db)
    project, created = upsert_project(db, project_in)
    results_saved = save_bid_results(db, project, bid_results_in)
    if bid_results_in:
        calculate_bid_deltas(db, project)
        calculate_project_analytics(db, project)
    db.commit()
    return {
        "project_name": project.project_name,
        "external_id": project.external_id,
        "engineer_estimate": project.engineer_estimate,
        "bid_results_saved": results_saved,
        "created": created,
    }


@app.post("/api/manual-import")
async def api_manual_import(payload: ManualImportIn, db: Session = Depends(get_db)):
    from app.tasks import upsert_project, save_bid_results, seed_sources
    seed_sources(db)

    parsed = parse_project_text(payload.raw_text, payload.import_type)
    project_in = parsed["project"]
    bid_results_in = parsed["bid_results"]

    project, created = upsert_project(db, project_in)
    results_saved = save_bid_results(db, project, bid_results_in)

    if project.bid_results:
        from app.analytics import calculate_bid_deltas, calculate_project_analytics
        calculate_bid_deltas(db, project)
        calculate_project_analytics(db, project)

    db.commit()

    return {
        "project_id": project.id,
        "project_name": project.project_name,
        "created": created,
        "relevance_score": project.relevance_score,
        "relevance_reason": project.relevance_reason,
        "planholders_parsed": len(parsed["planholders"]),
        "bid_results_saved": results_saved,
    }


@app.get("/api/export-csv/{table}")
async def api_export_csv(table: str, db: Session = Depends(get_db)):
    exports = export_csv(db)
    if table not in exports:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found. Available: {list(exports.keys())}")
    content = exports[table]
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table}.csv"},
    )


@app.get("/api/export-csv")
async def api_export_all_csv(db: Session = Depends(get_db)):
    exports = export_csv(db)
    import zipfile, io as _io
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in exports.items():
            zf.writestr(f"{name}.csv", content)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=bid_intel_export.zip"},
    )
