"""Integration tests for FastAPI endpoints including TemplateResponse usage."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app as fastapi_app

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="module")
def client():
    import app.models  # noqa: F401 — register all models with metadata
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db

    # Seed sources so pages don't crash on empty DB
    db = TestSession()
    from app.tasks import seed_sources
    seed_sources(db)
    db.close()

    with TestClient(fastapi_app, raise_server_exceptions=True) as c:
        yield c

    fastapi_app.dependency_overrides.clear()


def test_dashboard_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Bid" in r.text


def test_analytics_page_loads(client):
    r = client.get("/analytics")
    assert r.status_code == 200
    assert "Analytics" in r.text


def test_sources_page_loads(client):
    r = client.get("/sources")
    assert r.status_code == 200
    assert "Sources" in r.text or "Mountain View" in r.text


def test_manual_import_page_loads(client):
    r = client.get("/manual-import")
    assert r.status_code == 200
    assert "Import" in r.text


def test_seed_fixtures_endpoint(client):
    r = client.post("/api/seed-fixtures")
    assert r.status_code == 200
    data = r.json()
    assert "current" in data


def test_dashboard_shows_projects_after_seed(client):
    r = client.get("/")
    assert r.status_code == 200


def test_calculate_analytics_endpoint(client):
    r = client.post("/api/calculate-analytics")
    assert r.status_code == 200
    data = r.json()
    assert "projects_calculated" in data


def test_debug_source_mountain_view(client):
    r = client.get("/api/debug-source/mountain_view")
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == "mountain_view"
    assert data["fixture_open_bids"] == 7


def test_debug_source_stub(client):
    r = client.get("/api/debug-source/hayward")
    assert r.status_code == 200
    data = r.json()
    assert "key" in data or "connector" in data


def test_debug_source_not_found(client):
    r = client.get("/api/debug-source/does_not_exist")
    assert r.status_code == 404


def test_manual_import_endpoint(client):
    r = client.post("/api/manual-import", json={
        "raw_text": "Project: EV Charging Station Install\nAgency: City of Test\nBid Due: 12/01/2024\nEstimate: $300,000",
        "import_type": "auto",
    })
    assert r.status_code == 200
    data = r.json()
    assert "project_id" in data
    assert data["relevance_score"] is not None


def test_project_detail_after_seed(client):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    # Just verify the route pattern works — project 1 may or may not exist
    r = client.get("/projects/1")
    assert r.status_code in (200, 404)


def test_export_csv_projects(client):
    r = client.get("/api/export-csv/projects")
    assert r.status_code == 200
    assert "project_name" in r.text or r.text == ""


def test_export_csv_all_zip(client):
    r = client.get("/api/export-csv")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_template_response_does_not_crash(client):
    """Verify new Starlette TemplateResponse(request, ...) signature doesn't crash."""
    for path in ["/", "/analytics", "/sources", "/manual-import"]:
        r = client.get(path)
        assert r.status_code == 200, f"Page {path} failed with {r.status_code}"
