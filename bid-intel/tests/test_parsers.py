import pytest
from pathlib import Path
from app.connectors.mountain_view import (
    MountainViewConnector, _parse_open_bids, _parse_archive_rows, _parse_money, _parse_date
)
from app.connectors.manual_import import parse_project_text
from app.connectors.email_import import parse_email_text
from bs4 import BeautifulSoup

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def mv_soup():
    html = (FIXTURES_DIR / "mountain_view_sample.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_parse_money():
    assert _parse_money("$485,000") == 485000.0
    assert _parse_money("$1,200,000") == 1200000.0
    assert _parse_money("") is None
    assert _parse_money("N/A") is None


def test_parse_date():
    from datetime import date
    assert _parse_date("2024-08-15") == date(2024, 8, 15)
    assert _parse_date("08/15/2024") == date(2024, 8, 15)
    assert _parse_date("") is None


def test_fixture_open_bids_count(mv_soup):
    projects = _parse_open_bids(mv_soup)
    assert len(projects) == 7


def test_fixture_open_bid_names(mv_soup):
    projects = _parse_open_bids(mv_soup)
    names = [p.project_name for p in projects]
    assert any("Electrical" in n or "electrical" in n for n in names)
    assert any("Fire Alarm" in n or "fire alarm" in n.lower() for n in names)


def test_fixture_open_bids_have_estimates(mv_soup):
    projects = _parse_open_bids(mv_soup)
    with_estimates = [p for p in projects if p.engineer_estimate]
    assert len(with_estimates) > 0


def test_fixture_open_bids_agency(mv_soup):
    projects = _parse_open_bids(mv_soup)
    for p in projects:
        assert p.agency_owner == "City of Mountain View"


def test_fixture_archived_bids_count(mv_soup):
    pairs = _parse_archive_rows(mv_soup)
    assert len(pairs) == 2


def test_fixture_archived_has_bid_results(mv_soup):
    pairs = _parse_archive_rows(mv_soup)
    for proj, results in pairs:
        assert len(results) > 0


def test_fixture_archived_low_bidder(mv_soup):
    pairs = _parse_archive_rows(mv_soup)
    for proj, results in pairs:
        low_bids = [r for r in results if r.is_low_bidder]
        assert len(low_bids) >= 1


def test_fixture_archived_is_archived_flag(mv_soup):
    pairs = _parse_archive_rows(mv_soup)
    for proj, _ in pairs:
        assert proj.is_archived is True


def test_connector_fixture_mode():
    conn = MountainViewConnector(fixture=True)
    projects = conn.fetch_current_projects()
    assert len(projects) == 7


def test_connector_debug():
    conn = MountainViewConnector(fixture=True)
    debug = conn.debug_source()
    assert debug["fixture_exists"] is True
    assert debug["fixture_open_bids"] == 7
    assert debug["fixture_archived_bids"] == 2
    assert debug["status"] == "ok"


def test_manual_import_extracts_project():
    text = """
Bid Title: City Hall Electrical Upgrade
Agency: City of Sunnyvale
Bid Due: 09/15/2024
Engineer's Estimate: $450,000
https://www.sunnyvale.ca.gov/bids/123
Description: Switchgear and panelboard replacement
"""
    result = parse_project_text(text)
    assert result["project"].project_name != ""
    assert result["project"].estimate_value == 450000.0


def test_manual_import_extracts_bid_results():
    text = """
Project: Park Security Cameras
ABC Security — $150,000 (Low Bidder, Awarded)
XYZ Systems — $175,000
"""
    result = parse_project_text(text)
    assert len(result["bid_results"]) >= 1
    low = [r for r in result["bid_results"] if r.is_low_bidder]
    assert len(low) >= 1


def test_email_import_extracts_basic():
    text = """
Bid: Library Fire Alarm Replacement
Agency: City of Hayward
Bid Date: 10/01/2024
Estimate: $180,000
"""
    project = parse_email_text(text)
    assert project is not None
    assert project.estimate_value == 180000.0
