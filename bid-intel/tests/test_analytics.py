import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Project, Company, BidResult, Planholder, ProjectBidAnalytics
from app.analytics import (
    calculate_bid_deltas, calculate_project_analytics,
    calculate_all_analytics, get_trend_analytics
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def project_with_bids(db):
    project = Project(
        project_name="Test Electrical Project",
        agency_owner="Test Agency",
        engineer_estimate=500000.0,
        status="bid_opened",
        is_archived=True,
    )
    db.add(project)
    db.flush()

    c1 = Company(name="Alpha Electric", normalized_name="alpha electric")
    c2 = Company(name="Beta Electric", normalized_name="beta electric")
    c3 = Company(name="Gamma Electric", normalized_name="gamma electric")
    db.add_all([c1, c2, c3])
    db.flush()

    ph1 = Planholder(project_id=project.id, company_id=c1.id, listed_as="Alpha Electric")
    ph2 = Planholder(project_id=project.id, company_id=c2.id, listed_as="Beta Electric")
    ph3 = Planholder(project_id=project.id, company_id=c3.id, listed_as="Gamma Electric")
    db.add_all([ph1, ph2, ph3])

    r1 = BidResult(project_id=project.id, company_id=c1.id, bid_amount=450000.0, is_awarded=True, result_date=date(2024, 5, 1))
    r2 = BidResult(project_id=project.id, company_id=c2.id, bid_amount=480000.0, result_date=date(2024, 5, 1))
    r3 = BidResult(project_id=project.id, company_id=c3.id, bid_amount=520000.0, result_date=date(2024, 5, 1))
    db.add_all([r1, r2, r3])
    db.flush()

    return project


def test_calculate_bid_deltas(db, project_with_bids):
    calculate_bid_deltas(db, project_with_bids)
    results = db.query(BidResult).filter_by(project_id=project_with_bids.id).order_by(BidResult.bid_amount).all()

    assert results[0].bid_rank == 1
    assert results[0].is_low_bidder is True
    assert results[0].delta_from_low_amount == 0.0 or results[0].delta_from_low_amount is not None
    assert results[1].bid_rank == 2
    assert results[2].bid_rank == 3


def test_delta_from_low(db, project_with_bids):
    calculate_bid_deltas(db, project_with_bids)
    results = db.query(BidResult).filter_by(project_id=project_with_bids.id).order_by(BidResult.bid_amount).all()
    assert results[1].delta_from_low_amount == pytest.approx(30000.0)
    assert results[2].delta_from_low_amount == pytest.approx(70000.0)


def test_delta_from_engineer_estimate(db, project_with_bids):
    calculate_bid_deltas(db, project_with_bids)
    results = db.query(BidResult).filter_by(project_id=project_with_bids.id).order_by(BidResult.bid_amount).all()
    assert results[0].delta_from_engineer_estimate_amount == pytest.approx(-50000.0)


def test_calculate_project_analytics(db, project_with_bids):
    calculate_bid_deltas(db, project_with_bids)
    analytics = calculate_project_analytics(db, project_with_bids)

    assert analytics.planholders_count == 3
    assert analytics.actual_bidders_count == 3
    assert analytics.non_bidding_planholders_count == 0
    assert analytics.bid_participation_rate == pytest.approx(100.0)
    assert analytics.low_bid_amount == pytest.approx(450000.0)
    assert analytics.second_bid_amount == pytest.approx(480000.0)
    assert analytics.high_bid_amount == pytest.approx(520000.0)


def test_participation_rate_with_non_bidders(db):
    project = Project(project_name="Test", agency_owner="Test Agency", status="bid_opened", is_archived=True)
    db.add(project)
    db.flush()

    c1 = Company(name="Bidder", normalized_name="bidder")
    c2 = Company(name="No Bid", normalized_name="no bid")
    db.add_all([c1, c2])
    db.flush()

    db.add(Planholder(project_id=project.id, company_id=c1.id))
    db.add(Planholder(project_id=project.id, company_id=c2.id))
    db.add(BidResult(project_id=project.id, company_id=c1.id, bid_amount=100000.0))
    db.flush()

    analytics = calculate_project_analytics(db, project)
    assert analytics.planholders_count == 2
    assert analytics.actual_bidders_count == 1
    assert analytics.non_bidding_planholders_count == 1
    assert analytics.bid_participation_rate == pytest.approx(50.0)


def test_low_to_second_delta(db, project_with_bids):
    calculate_bid_deltas(db, project_with_bids)
    analytics = calculate_project_analytics(db, project_with_bids)
    assert analytics.low_to_second_delta_amount == pytest.approx(30000.0)
    assert analytics.low_to_second_delta_percent == pytest.approx(6.67, abs=0.1)


def test_calculate_all_analytics(db, project_with_bids):
    count = calculate_all_analytics(db)
    assert count >= 1
    a = db.query(ProjectBidAnalytics).filter_by(project_id=project_with_bids.id).first()
    assert a is not None


def test_trend_analytics_empty_db(db):
    trends = get_trend_analytics(db)
    assert "top_bidders" in trends
    assert "top_winners" in trends
    assert "agency_stats" in trends
    assert isinstance(trends["top_bidders"], list)
