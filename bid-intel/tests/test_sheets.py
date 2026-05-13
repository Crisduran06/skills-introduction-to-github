import pytest
import types
from datetime import datetime
from app.sheets import format_project_row, format_bid_result_row, sync_to_sheets


def _make_project(**kwargs):
    defaults = dict(
        id=1,
        project_name="Test Electrical Project",
        agency_owner="City of Mountain View",
        location_city="Mountain View",
        bid_due_date=None,
        status="open",
        relevance_score=5,
        estimate_value=500000.0,
        source_url="https://example.com",
        created_at=datetime(2024, 1, 1),
        is_archived=False,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_bid_result(**kwargs):
    defaults = dict(
        id=1, project_id=1, company_id=2,
        bid_amount=450000.0, bid_rank=1,
        is_low_bidder=True, is_awarded=True,
        delta_from_low_amount=0.0, delta_from_low_percent=0.0,
        delta_from_engineer_estimate_percent=-10.0,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_format_project_row_length():
    row = format_project_row(_make_project())
    assert len(row) == 10


def test_format_project_row_values():
    row = format_project_row(_make_project())
    assert row[0] == 1
    assert row[1] == "Test Electrical Project"
    assert row[2] == "City of Mountain View"
    assert row[6] == 5


def test_format_bid_result_row_length():
    row = format_bid_result_row(_make_bid_result())
    assert len(row) == 10


def test_format_bid_result_awarded():
    row = format_bid_result_row(_make_bid_result(is_awarded=True))
    assert "Yes" in row


def test_sync_to_sheets_no_credentials():
    """Sheets sync should gracefully skip when not configured."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    result = sync_to_sheets(db)
    db.close()
    assert result["status"] in ("skipped", "error")
