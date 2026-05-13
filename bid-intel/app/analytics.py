from __future__ import annotations
from datetime import datetime
from statistics import median, mean
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.models import (
    Project, BidResult, Planholder, ProjectBidAnalytics,
    CompanyProjectParticipation, Company,
)


def _pct(a: float, b: float) -> Optional[float]:
    if b and b != 0:
        return round((a - b) / b * 100, 2)
    return None


def calculate_bid_deltas(db: Session, project: Project) -> None:
    results = (
        db.query(BidResult)
        .filter(BidResult.project_id == project.id, BidResult.bid_amount.isnot(None))
        .order_by(BidResult.bid_amount)
        .all()
    )
    if not results:
        return

    low = results[0].bid_amount
    prev = None
    ee = project.engineer_estimate

    for i, r in enumerate(results):
        r.bid_rank = i + 1
        r.is_low_bidder = i == 0
        r.delta_from_low_amount = round(r.bid_amount - low, 2) if r.bid_amount is not None else None
        r.delta_from_low_percent = _pct(r.bid_amount, low)
        r.delta_from_previous_amount = round(r.bid_amount - prev, 2) if prev is not None else None
        r.delta_from_previous_percent = _pct(r.bid_amount, prev) if prev is not None else None
        r.delta_from_engineer_estimate_amount = round(r.bid_amount - ee, 2) if ee else None
        r.delta_from_engineer_estimate_percent = _pct(r.bid_amount, ee) if ee else None
        prev = r.bid_amount

    db.flush()


def calculate_project_analytics(db: Session, project: Project) -> ProjectBidAnalytics:
    results = (
        db.query(BidResult)
        .filter(BidResult.project_id == project.id, BidResult.bid_amount.isnot(None))
        .order_by(BidResult.bid_amount)
        .all()
    )
    planholders = db.query(Planholder).filter(Planholder.project_id == project.id).all()

    amounts = [r.bid_amount for r in results if r.bid_amount is not None]
    ph_count = len(planholders)
    bidder_count = len(amounts)
    non_bidding = max(0, ph_count - bidder_count)
    participation_rate = round(bidder_count / ph_count * 100, 2) if ph_count > 0 else None

    low_bid = amounts[0] if amounts else None
    second_bid = amounts[1] if len(amounts) > 1 else None
    high_bid = amounts[-1] if amounts else None
    avg_bid = round(mean(amounts), 2) if amounts else None
    med_bid = round(median(amounts), 2) if amounts else None

    low_to_second_amt = round(second_bid - low_bid, 2) if second_bid and low_bid else None
    low_to_second_pct = _pct(second_bid, low_bid) if second_bid and low_bid else None
    low_to_high_amt = round(high_bid - low_bid, 2) if high_bid and low_bid else None
    low_to_high_pct = _pct(high_bid, low_bid) if high_bid and low_bid else None

    ee = project.engineer_estimate
    low_vs_ee_amt = round(low_bid - ee, 2) if low_bid and ee else None
    low_vs_ee_pct = _pct(low_bid, ee) if low_bid and ee else None

    existing = db.query(ProjectBidAnalytics).filter_by(project_id=project.id).first()
    if existing:
        analytics = existing
    else:
        analytics = ProjectBidAnalytics(project_id=project.id)
        db.add(analytics)

    analytics.planholders_count = ph_count
    analytics.actual_bidders_count = bidder_count
    analytics.non_bidding_planholders_count = non_bidding
    analytics.bid_participation_rate = participation_rate
    analytics.low_bid_amount = low_bid
    analytics.second_bid_amount = second_bid
    analytics.high_bid_amount = high_bid
    analytics.average_bid_amount = avg_bid
    analytics.median_bid_amount = med_bid
    analytics.low_to_second_delta_amount = low_to_second_amt
    analytics.low_to_second_delta_percent = low_to_second_pct
    analytics.low_to_high_delta_amount = low_to_high_amt
    analytics.low_to_high_delta_percent = low_to_high_pct
    analytics.engineer_estimate = ee
    analytics.low_bid_vs_engineer_estimate_amount = low_vs_ee_amt
    analytics.low_bid_vs_engineer_estimate_percent = low_vs_ee_pct
    analytics.calculated_at = datetime.utcnow()

    db.flush()
    return analytics


def rebuild_company_participation(db: Session, project: Project) -> None:
    db.query(CompanyProjectParticipation).filter_by(project_id=project.id).delete()

    planholders = db.query(Planholder).filter_by(project_id=project.id).all()
    results = db.query(BidResult).filter_by(project_id=project.id).all()

    company_ids: set[int] = set()
    for ph in planholders:
        if ph.company_id:
            company_ids.add(ph.company_id)
    for r in results:
        if r.company_id:
            company_ids.add(r.company_id)

    for cid in company_ids:
        ph = next((p for p in planholders if p.company_id == cid), None)
        bid = next((r for r in results if r.company_id == cid), None)
        cpp = CompanyProjectParticipation(
            project_id=project.id,
            company_id=cid,
            was_planholder=ph is not None,
            submitted_bid=bid is not None,
            was_low_bidder=bid.is_low_bidder if bid else False,
            was_awarded=bid.is_awarded if bid else False,
            bid_amount=bid.bid_amount if bid else None,
            bid_rank=bid.bid_rank if bid else None,
        )
        db.add(cpp)

    db.flush()


def calculate_all_analytics(db: Session) -> int:
    projects_with_results = (
        db.query(Project)
        .join(BidResult, BidResult.project_id == Project.id)
        .distinct()
        .all()
    )
    count = 0
    for project in projects_with_results:
        calculate_bid_deltas(db, project)
        calculate_project_analytics(db, project)
        rebuild_company_participation(db, project)
        count += 1
    db.commit()
    return count


def get_trend_analytics(db: Session) -> dict:
    top_bidders = (
        db.query(Company.name, func.count(BidResult.id).label("bid_count"))
        .join(BidResult, BidResult.company_id == Company.id)
        .group_by(Company.id)
        .order_by(desc("bid_count"))
        .limit(15)
        .all()
    )

    top_winners = (
        db.query(Company.name, func.count(BidResult.id).label("win_count"))
        .join(BidResult, BidResult.company_id == Company.id)
        .filter(BidResult.is_awarded == True)  # noqa: E712
        .group_by(Company.id)
        .order_by(desc("win_count"))
        .limit(15)
        .all()
    )

    top_planholders = (
        db.query(Company.name, func.count(Planholder.id).label("ph_count"))
        .join(Planholder, Planholder.company_id == Company.id)
        .group_by(Company.id)
        .order_by(desc("ph_count"))
        .limit(15)
        .all()
    )

    non_bidders = (
        db.query(Company.name, func.count(CompanyProjectParticipation.project_id).label("cnt"))
        .join(CompanyProjectParticipation, CompanyProjectParticipation.company_id == Company.id)
        .filter(
            CompanyProjectParticipation.was_planholder == True,  # noqa: E712
            CompanyProjectParticipation.submitted_bid == False,  # noqa: E712
        )
        .group_by(Company.id)
        .order_by(desc("cnt"))
        .limit(15)
        .all()
    )

    agency_stats_raw = (
        db.query(
            Project.agency_owner,
            func.avg(ProjectBidAnalytics.actual_bidders_count).label("avg_bidders"),
            func.avg(ProjectBidAnalytics.planholders_count).label("avg_planholders"),
            func.avg(ProjectBidAnalytics.bid_participation_rate).label("avg_participation"),
            func.avg(ProjectBidAnalytics.low_to_second_delta_percent).label("avg_low_to_second"),
            func.avg(ProjectBidAnalytics.low_to_high_delta_percent).label("avg_low_to_high"),
            func.count(ProjectBidAnalytics.project_id).label("project_count"),
        )
        .join(ProjectBidAnalytics, ProjectBidAnalytics.project_id == Project.id)
        .filter(Project.agency_owner.isnot(None))
        .group_by(Project.agency_owner)
        .order_by(desc("project_count"))
        .all()
    )

    return {
        "top_bidders": [{"name": r.name, "bid_count": r.bid_count} for r in top_bidders],
        "top_winners": [{"name": r.name, "win_count": r.win_count} for r in top_winners],
        "top_planholders": [{"name": r.name, "ph_count": r.ph_count} for r in top_planholders],
        "non_bidders": [{"name": r.name, "count": r.cnt} for r in non_bidders],
        "agency_stats": [
            {
                "agency": r.agency_owner,
                "avg_bidders": round(r.avg_bidders, 1) if r.avg_bidders else None,
                "avg_planholders": round(r.avg_planholders, 1) if r.avg_planholders else None,
                "avg_participation": round(r.avg_participation, 1) if r.avg_participation else None,
                "avg_low_to_second_pct": round(r.avg_low_to_second, 1) if r.avg_low_to_second else None,
                "avg_low_to_high_pct": round(r.avg_low_to_high, 1) if r.avg_low_to_high else None,
                "project_count": r.project_count,
            }
            for r in agency_stats_raw
        ],
    }
