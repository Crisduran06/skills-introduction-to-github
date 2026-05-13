"""Core task functions used by CLI, API endpoints, and the scheduler."""
from __future__ import annotations
import csv
import io
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import (
    Source, Project, Company, Planholder,
    BidResult, ProjectBidAnalytics, CompanyProjectParticipation,
)
from app.schemas import ProjectIn, PlanholderIn, BidResultIn
from app.scoring import score_project
from app.dedupe import find_duplicate, merge_project, normalize_company_name
from app.analytics import calculate_all_analytics


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------

SOURCE_SEED_DATA = [
    dict(name="Mountain View Official Bids", key="mountain_view", base_url="https://www.mountainview.gov/depts/pw/purchasing/default.asp", platform_type="public_page", status="fixture_only", scrape_allowed=True, auth_required=False, supports_current_bids=True, supports_bid_results=True, supports_awards=True, supports_archives=True, notes="Public page. Fixture connector implemented."),
    dict(name="Mountain View BidNet Direct", key="mountain_view_bidnet", base_url="https://www.bidnetdirect.com", platform_type="bidnet", status="manual_only", scrape_allowed=False, auth_required=True, notes="BidNet requires login. Use manual import."),
    dict(name="Hayward Public Works", key="hayward", base_url="https://www.hayward-ca.gov/business/purchasing/bids-rfps", platform_type="public_page", status="stub", scrape_allowed=True, auth_required=False, supports_current_bids=True, notes="Stub — implement parser when page structure confirmed."),
    dict(name="Sunnyvale PlanetBids", key="sunnyvale", base_url="https://pbsystem.planetbids.com", platform_type="planetbids", status="stub", scrape_allowed=False, auth_required=True, notes="PlanetBids portal — login required for detail. Manual import supported."),
    dict(name="San Mateo County Public Works", key="san_mateo_county", base_url="https://www.smcgov.org/public-works/bids", platform_type="public_page", status="stub", scrape_allowed=True, auth_required=False, supports_current_bids=True),
    dict(name="Alameda County Public Works", key="alameda_county", base_url="https://www.acgov.org/gsa/purchasing", platform_type="public_page", status="stub", scrape_allowed=True, auth_required=False, supports_current_bids=True),
    dict(name="EBMUD Construction Bids", key="ebmud", base_url="https://construction-bids.ebmud.com/CurrentorFutureBid.aspx?BidMode=Current", platform_type="public_page", status="live", scrape_allowed=True, auth_required=False, supports_current_bids=True, notes="ASP.NET WebForms — static HTML table, no login required."),
    dict(name="Valley Water PlanetBids", key="valley_water", base_url="https://pbsystem.planetbids.com/portal/35898/portal-detail", platform_type="planetbids", status="stub", scrape_allowed=False, auth_required=True, notes="PlanetBids — planholder detail requires login."),
    dict(name="Port of Oakland", key="port_oakland", base_url="https://www.portofoakland.com/business/bids-rfp-center/engineering-bids-rfps-rfqs", platform_type="public_page", status="live", scrape_allowed=True, auth_required=False, supports_current_bids=True, notes="WordPress CMS. BidNet links skipped (requires login)."),
    dict(name="SFPUC / SF Bids", key="sfpuc", base_url="https://webapps.sfpuc.org/bids/bidlist.aspx?bidtype=5", platform_type="public_page", status="live", scrape_allowed=True, auth_required=False, supports_current_bids=True, notes="ASP.NET WebForms — shows contract numbers and dollar estimates publicly."),
    dict(name="SF Public Works", key="sf_public_works", base_url="https://bidopportunities.apps.sfdpw.org/", platform_type="public_page", status="live", scrape_allowed=True, auth_required=False, supports_current_bids=True, notes="ASP.NET MVC — shows estimates. Document download requires BSM login."),
    dict(name="Oakland Capital Contracts", key="oakland", base_url="https://apps.oaklandca.gov/ContractOpportunities/Opportunities", platform_type="public_page", status="live", scrape_allowed=True, auth_required=False, supports_current_bids=True, notes="May be JS-rendered — returns empty if SPA shell detected."),
    dict(name="SFO Procurement", key="sfo", base_url="https://www.flysfo.com/business/contracts-procurement", platform_type="public_page", status="stub", scrape_allowed=True, auth_required=False, supports_current_bids=True),
    dict(name="BART Procurement", key="bart", base_url="https://www.bart.gov/about/business/procurement/contractsout", platform_type="public_page", status="live", scrape_allowed=True, auth_required=False, supports_current_bids=True, supports_archives=True, notes="Drupal CMS — static HTML, no login required."),
    dict(name="VTA Procurement", key="vta", base_url="https://procurement.opengov.com/portal/vta", platform_type="opengov", status="stub", scrape_allowed=False, auth_required=False, notes="OpenGov React SPA — requires Playwright or API interception. Manual import supported."),
    dict(name="Santa Clara County Procurement", key="santa_clara_county", base_url="https://www.sccgov.org/sites/oa/Pages/Procurement.aspx", platform_type="public_page", status="stub", scrape_allowed=True, auth_required=False, supports_current_bids=True),
    dict(name="BXSCCO Weekly Bidding PDF", key="bxscco", base_url="https://www.bxscco.com", platform_type="pdf_bulletin", status="stub", scrape_allowed=False, auth_required=True, notes="Weekly PDF bulletin — membership may be required."),
    dict(name="Bay Area Builders Exchange / CalBX", key="builders_exchange", base_url="https://www.calbx.com", platform_type="pdf_bulletin", status="stub", scrape_allowed=False, auth_required=True, notes="CalBX requires membership. Check public listing availability."),
]


def get_connector(key: str, fixture: bool = False):
    """Return a connector instance for the given source key."""
    if key == "mountain_view":
        from app.connectors.mountain_view import MountainViewConnector
        return MountainViewConnector(fixture=fixture)
    if key == "ebmud":
        from app.connectors.ebmud import EbmudConnector
        return EbmudConnector()
    if key == "bart":
        from app.connectors.bart import BartConnector
        return BartConnector()
    if key == "sfpuc":
        from app.connectors.sfpuc import SfpucConnector
        return SfpucConnector()
    if key == "sf_public_works":
        from app.connectors.sfpuc import SfPublicWorksConnector
        return SfPublicWorksConnector()
    if key == "port_oakland":
        from app.connectors.port_oakland import PortOaklandConnector
        return PortOaklandConnector()
    if key == "oakland":
        from app.connectors.oakland import OaklandConnector
        return OaklandConnector()
    return None


def seed_sources(db: Session) -> int:
    count = 0
    for data in SOURCE_SEED_DATA:
        existing = db.query(Source).filter_by(key=data["key"]).first()
        if not existing:
            source = Source(**data)
            db.add(source)
            count += 1
    db.commit()
    return count


def get_or_create_company(db: Session, name: str) -> Company:
    norm = normalize_company_name(name)
    company = db.query(Company).filter_by(normalized_name=norm).first()
    if not company:
        company = Company(name=name, normalized_name=norm)
        db.add(company)
        db.flush()
    return company


def upsert_project(db: Session, incoming: ProjectIn) -> tuple[Project, bool]:
    """Insert or merge a project. Returns (project, created)."""
    existing = find_duplicate(db, incoming)
    if existing:
        merge_project(existing, incoming)
        existing.last_checked_at = datetime.utcnow()
        db.flush()
        return existing, False

    score, reason = score_project(
        incoming.project_name,
        incoming.description or "",
        incoming.trade_scope_raw or "",
    )
    project = Project(
        **incoming.model_dump(),
        relevance_score=score,
        relevance_reason=reason,
        last_checked_at=datetime.utcnow(),
    )
    db.add(project)
    db.flush()
    return project, True


def save_bid_results(db: Session, project: Project, results: list[BidResultIn]) -> int:
    count = 0
    for r in results:
        company = None
        if r.listed_as:
            company = get_or_create_company(db, r.listed_as)

        existing = db.query(BidResult).filter_by(
            project_id=project.id,
            company_id=company.id if company else None,
        ).first() if company else None

        if existing:
            if r.bid_amount:
                existing.bid_amount = r.bid_amount
            existing.is_low_bidder = r.is_low_bidder
            existing.is_awarded = r.is_awarded
        else:
            br = BidResult(
                project_id=project.id,
                company_id=company.id if company else None,
                bid_amount=r.bid_amount,
                is_low_bidder=r.is_low_bidder,
                is_awarded=r.is_awarded,
                result_date=r.result_date,
                responsive_status=r.responsive_status,
                notes=r.notes,
                source_url=r.source_url,
            )
            db.add(br)
            count += 1
    db.flush()
    return count


def fetch_source(db: Session, key: str, fixture: bool = False, archives: bool = False) -> dict:
    source = db.query(Source).filter_by(key=key).first()
    if not source:
        return {"error": f"Source '{key}' not found"}

    connector = get_connector(key, fixture=fixture)
    if not connector:
        return {"status": "stub", "message": f"No connector implemented for '{key}'"}

    projects_added = 0
    projects_updated = 0
    results_added = 0

    if archives:
        if hasattr(connector, "fetch_archived_with_results"):
            pairs = connector.fetch_archived_with_results()
            for proj_in, bid_results_in in pairs:
                proj_in.source_id = source.id
                project, created = upsert_project(db, proj_in)
                if created:
                    projects_added += 1
                else:
                    projects_updated += 1
                results_added += save_bid_results(db, project, bid_results_in)
        else:
            archived = connector.fetch_archived_projects()
            for proj_in in archived:
                proj_in.source_id = source.id
                _, created = upsert_project(db, proj_in)
                if created:
                    projects_added += 1
                else:
                    projects_updated += 1
    else:
        current = connector.fetch_current_projects()
        for proj_in in current:
            proj_in.source_id = source.id
            _, created = upsert_project(db, proj_in)
            if created:
                projects_added += 1
            else:
                projects_updated += 1

    source.last_checked_at = datetime.utcnow()
    db.commit()

    return {
        "source": key,
        "fixture": fixture,
        "archives": archives,
        "projects_added": projects_added,
        "projects_updated": projects_updated,
        "results_added": results_added,
    }


def fetch_all_sources(db: Session, fixture: bool = False) -> list[dict]:
    sources = db.query(Source).filter(
        Source.status.in_(["live", "fixture_only"]),
        Source.supports_current_bids == True,  # noqa: E712
    ).all()
    results = []
    for source in sources:
        results.append(fetch_source(db, source.key, fixture=fixture))
    return results


def fetch_all_archives(db: Session, fixture: bool = False) -> list[dict]:
    sources = db.query(Source).filter(
        Source.status.in_(["live", "fixture_only"]),
        Source.supports_archives == True,  # noqa: E712
    ).all()
    results = []
    for source in sources:
        results.append(fetch_source(db, source.key, fixture=fixture, archives=True))
    return results


def seed_fixtures(db: Session) -> dict:
    """Load fixture data for all implemented connectors."""
    seed_sources(db)
    current_result = fetch_source(db, "mountain_view", fixture=True, archives=False)
    archive_result = fetch_source(db, "mountain_view", fixture=True, archives=True)
    analytics_count = calculate_all_analytics(db)
    return {
        "current": current_result,
        "archives": archive_result,
        "analytics_calculated": analytics_count,
    }


def export_csv(db: Session) -> dict[str, str]:
    """Return dict of table_name -> CSV string."""
    exports: dict[str, str] = {}

    def to_csv(rows: list[dict]) -> str:
        if not rows:
            return ""
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return out.getvalue()

    projects = db.query(Project).all()
    exports["projects"] = to_csv([{
        "id": p.id, "project_name": p.project_name, "agency_owner": p.agency_owner,
        "location_city": p.location_city, "bid_due_date": p.bid_due_date,
        "status": p.status, "relevance_score": p.relevance_score,
        "estimate_value": p.estimate_value, "engineer_estimate": p.engineer_estimate,
        "source_url": p.source_url, "is_archived": p.is_archived,
        "created_at": p.created_at,
    } for p in projects])

    sources = db.query(Source).all()
    exports["sources"] = to_csv([{
        "id": s.id, "name": s.name, "key": s.key, "platform_type": s.platform_type,
        "status": s.status, "auth_required": s.auth_required,
        "supports_current_bids": s.supports_current_bids,
        "last_checked_at": s.last_checked_at,
    } for s in sources])

    companies = db.query(Company).all()
    exports["companies"] = to_csv([{
        "id": c.id, "name": c.name, "normalized_name": c.normalized_name,
        "company_type": c.company_type, "phone": c.phone, "email": c.email,
    } for c in companies])

    planholders = db.query(Planholder).all()
    exports["planholders"] = to_csv([{
        "id": ph.id, "project_id": ph.project_id, "company_id": ph.company_id,
        "listed_as": ph.listed_as, "contact_name": ph.contact_name,
        "date_added": ph.date_added,
    } for ph in planholders])

    bid_results = db.query(BidResult).all()
    exports["bid_results"] = to_csv([{
        "id": r.id, "project_id": r.project_id, "company_id": r.company_id,
        "bid_amount": r.bid_amount, "bid_rank": r.bid_rank,
        "is_low_bidder": r.is_low_bidder, "is_awarded": r.is_awarded,
        "delta_from_low_amount": r.delta_from_low_amount,
        "delta_from_low_percent": r.delta_from_low_percent,
        "result_date": r.result_date,
    } for r in bid_results])

    analytics = db.query(ProjectBidAnalytics).all()
    exports["project_bid_analytics"] = to_csv([{
        "project_id": a.project_id, "planholders_count": a.planholders_count,
        "actual_bidders_count": a.actual_bidders_count,
        "bid_participation_rate": a.bid_participation_rate,
        "low_bid_amount": a.low_bid_amount, "second_bid_amount": a.second_bid_amount,
        "high_bid_amount": a.high_bid_amount, "average_bid_amount": a.average_bid_amount,
        "low_to_second_delta_percent": a.low_to_second_delta_percent,
        "low_to_high_delta_percent": a.low_to_high_delta_percent,
    } for a in analytics])

    participations = db.query(CompanyProjectParticipation).all()
    exports["company_project_participation"] = to_csv([{
        "project_id": cp.project_id, "company_id": cp.company_id,
        "was_planholder": cp.was_planholder, "submitted_bid": cp.submitted_bid,
        "was_low_bidder": cp.was_low_bidder, "was_awarded": cp.was_awarded,
        "bid_amount": cp.bid_amount, "bid_rank": cp.bid_rank,
    } for cp in participations])

    return exports
