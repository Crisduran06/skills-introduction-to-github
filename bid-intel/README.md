---
title: Bid Intel
emoji: 🏗️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Bid Intel

Bay Area government construction bid intelligence platform for electrical contractors.

Tracks open public bid opportunities, planholders, bid results, bid prices, awards, bid deltas, archived bid history, and long-term bidding trends.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Initialize database and seed sources
python manage.py init-db

# Load sample data (fixture mode — no live scraping)
python manage.py fetch --source mountain_view --fixture
python manage.py fetch-archives --source mountain_view --fixture
python manage.py calculate-analytics

# Start the web server
python manage.py run-server
# → http://127.0.0.1:8000
```

## CLI Commands

```bash
python manage.py init-db                          # Create tables, seed sources
python manage.py migrate-db                       # Re-run create_all (safe on existing DB)
python manage.py list-sources                     # Show all configured sources
python manage.py debug-source mountain_view       # Debug a source connector
python manage.py fetch --source mountain_view --fixture    # Load fixture data
python manage.py fetch --source mountain_view              # Fetch live page
python manage.py fetch --all                               # Fetch all live sources
python manage.py fetch-archives --source mountain_view --fixture
python manage.py fetch-archives --all
python manage.py calculate-analytics              # Calculate bid deltas and analytics
python manage.py export-csv --output ./exports    # Export all tables to CSV
python manage.py run-server --port 8000           # Start web server
```

## Web UI

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Open bids, relevance scores, action buttons |
| Project Detail | `/projects/{id}` | Bid results, planholders, deltas, analytics |
| Analytics | `/analytics` | Trends, top bidders, agency stats |
| Sources | `/sources` | Source status and debug |
| Manual Import | `/manual-import` | Paste raw text from any bid source |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/seed-fixtures` | Load all fixture data |
| `POST` | `/api/fetch-all` | Fetch all live sources |
| `POST` | `/api/fetch-archives` | Fetch all archived bids |
| `POST` | `/api/calculate-analytics` | Recalculate all analytics |
| `GET` | `/api/debug-source/{key}` | Debug a source |
| `POST` | `/api/manual-import` | Import pasted raw text |
| `GET` | `/api/export-csv/{table}` | Download a single table CSV |
| `GET` | `/api/export-csv` | Download all tables as ZIP |

## Source Status

| Key | Source | Status | Auth |
|-----|--------|--------|------|
| `mountain_view` | Mountain View Official Bids | Fixture + Live | No |
| `hayward` | Hayward Public Works | Stub | No |
| `ebmud` | EBMUD Construction Bids | Stub | No |
| `valley_water` | Valley Water PlanetBids | Stub | Login required |
| `sunnyvale` | Sunnyvale PlanetBids | Stub | Login required |
| `bart` | BART Procurement | Stub | No |
| `vta` | VTA Procurement | Stub | No |
| `sfpuc` | SFPUC / SF Bids | Stub | No |
| `sf_public_works` | SF Public Works | Stub | No |
| `oakland` | Oakland Capital Contracts | Stub | No |
| `port_oakland` | Port of Oakland | Stub | No |
| `sfo` | SFO Procurement | Stub | No |
| `santa_clara_county` | Santa Clara County | Stub | No |
| `san_mateo_county` | San Mateo County | Stub | No |
| `alameda_county` | Alameda County | Stub | No |
| `builders_exchange` | Bay Area Builders Exchange | Stub | Membership |
| `bxscco` | BXSCCO Weekly PDF | Stub | Membership |
| `mountain_view_bidnet` | Mountain View BidNet | Manual only | Login required |

## Manual Import

Paste any of these into `/manual-import`:
- Bid website listing
- Forwarded bid alert email
- Planholder list
- Bid tab / bid results table
- Award notice
- PDF text extract

The parser extracts project name, agency, city, dates, estimate, bidders, amounts, and awarded contractor. Relevance scoring is applied automatically.

## Relevance Scoring (1–5)

| Score | Meaning |
|-------|---------|
| 5 | Strong electrical/low-voltage scope clearly mentioned |
| 4 | MEP/building/facility project likely to include electrical |
| 3 | Civil/utility project that may include electrical |
| 2 | Unclear — needs manual plan review |
| 1 | Likely not relevant |

## Google Sheets Export (Optional)

```bash
pip install -e ".[sheets]"
```

Set in `.env`:
```
GOOGLE_SHEETS_CREDENTIALS_FILE=path/to/service_account.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
```

The app starts without Google credentials. Sheets sync is a no-op if not configured.

## Scheduler

Enable in `.env`:
```
SCHEDULER_ENABLED=true
FETCH_HOUR=6
RESULTS_CHECK_HOUR=7
SHEETS_SYNC_DAY=mon
```

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

## Project Structure

```
bid-intel/
  app/
    main.py          FastAPI app and routes
    models.py        SQLAlchemy ORM models
    schemas.py       Pydantic input/output schemas
    scoring.py       Relevance scoring engine
    dedupe.py        Project deduplication
    analytics.py     Bid delta and trend analytics
    sheets.py        Google Sheets export (optional)
    scheduler.py     APScheduler setup
    tasks.py         Core fetch/import/export logic
    cli.py           Typer CLI commands
    connectors/      Data source connectors
      base.py        Abstract base connector
      mountain_view.py  Mountain View (fixture + live)
      hayward.py     Stub
      [... more stubs]
      manual_import.py  Raw text parser
      email_import.py   Email body parser
    templates/       Jinja2 HTML templates
  tests/             pytest test suite (59 tests)
  fixtures/          Sample HTML files for fixture mode
  manage.py          CLI entry point
  pyproject.toml     Dependencies and build config
  .env.example       Environment variable reference
```
