import pytest
from datetime import date
from app.dedupe import normalize_company_name, find_duplicate, merge_project
from app.schemas import ProjectIn


def test_normalize_company_name():
    assert normalize_company_name("Bay Area Electric, Inc.") == "bay area electric"
    assert normalize_company_name("Silicon Valley LLC") == "silicon valley"
    assert normalize_company_name("Western Corp.") == "western"
    assert normalize_company_name("Peninsula Electric Co.") == "peninsula electric"


def test_normalize_strips_whitespace():
    assert normalize_company_name("  ABC Electric  ") == "abc electric"


def test_merge_does_not_overwrite_existing():
    from app.models import Project
    existing = Project(
        project_name="City Hall Electrical",
        estimate_value=500000.0,
        description="Existing description",
    )
    incoming = ProjectIn(
        project_name="City Hall Electrical",
        estimate_value=999999.0,
        description="New description attempt",
    )
    result = merge_project(existing, incoming)
    assert result.estimate_value == 500000.0
    assert result.description == "Existing description"


def test_merge_fills_missing_fields():
    from app.models import Project
    existing = Project(
        project_name="City Hall Electrical",
        estimate_value=None,
        description=None,
    )
    incoming = ProjectIn(
        project_name="City Hall Electrical",
        estimate_value=500000.0,
        description="New description",
        location_city="Mountain View",
    )
    result = merge_project(existing, incoming)
    assert result.estimate_value == 500000.0
    assert result.description == "New description"
    assert result.location_city == "Mountain View"


def test_merge_appends_source_url():
    from app.models import Project
    existing = Project(
        project_name="Test",
        source_url="https://example.com/1",
    )
    incoming = ProjectIn(
        project_name="Test",
        source_url="https://example.com/2",
    )
    result = merge_project(existing, incoming)
    assert "https://example.com/1" in result.source_url
    assert "https://example.com/2" in result.source_url
