from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional
import typer

app = typer.Typer(help="Bid Intel — Bay Area construction bid intelligence CLI")


def _get_db():
    from app.db import SessionLocal
    return SessionLocal()


@app.command("init-db")
def init_db():
    """Initialize the database (create tables)."""
    from app.db import init_db as _init_db
    _init_db()
    from app.tasks import seed_sources
    db = _get_db()
    try:
        count = seed_sources(db)
        typer.echo(f"Database initialized. {count} sources seeded.")
    finally:
        db.close()


@app.command("migrate-db")
def migrate_db():
    """Re-run table creation (safe to run on existing DB)."""
    from app.db import init_db as _init_db
    _init_db()
    typer.echo("Migration complete (SQLAlchemy create_all ran).")


@app.command("list-sources")
def list_sources():
    """List all configured bid sources."""
    from app.models import Source
    db = _get_db()
    try:
        sources = db.query(Source).order_by(Source.name).all()
        if not sources:
            typer.echo("No sources found. Run init-db first.")
            return
        typer.echo(f"{'Key':<30} {'Name':<40} {'Status':<15} {'Platform'}")
        typer.echo("-" * 100)
        for s in sources:
            typer.echo(f"{s.key:<30} {s.name:<40} {s.status:<15} {s.platform_type}")
    finally:
        db.close()


@app.command("debug-source")
def debug_source(key: str = typer.Argument(..., help="Source key, e.g. mountain_view")):
    """Debug a source connector."""
    from app.tasks import get_connector
    from app.models import Source
    import json

    connector = get_connector(key)
    if connector is None:
        db = _get_db()
        try:
            source = db.query(Source).filter_by(key=key).first()
            if source:
                typer.echo(f"Source '{key}' is a stub. Status: {source.status}. Notes: {source.notes}")
            else:
                typer.echo(f"Source '{key}' not found.")
        finally:
            db.close()
        return

    result = connector.debug_source()
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("fetch")
def fetch(
    source: Optional[str] = typer.Option(None, "--source", help="Source key to fetch"),
    fixture: bool = typer.Option(False, "--fixture", help="Use fixture data instead of live fetch"),
    all_sources: bool = typer.Option(False, "--all", help="Fetch all live sources"),
):
    """Fetch current open bids from a source."""
    from app.tasks import fetch_source, fetch_all_sources
    db = _get_db()
    try:
        if all_sources:
            results = fetch_all_sources(db, fixture=fixture)
            for r in results:
                typer.echo(f"  {r}")
        elif source:
            result = fetch_source(db, source, fixture=fixture, archives=False)
            typer.echo(result)
        else:
            typer.echo("Specify --source <key> or --all")
            raise typer.Exit(1)
    finally:
        db.close()


@app.command("fetch-archives")
def fetch_archives(
    source: Optional[str] = typer.Option(None, "--source", help="Source key"),
    fixture: bool = typer.Option(False, "--fixture", help="Use fixture data"),
    all_sources: bool = typer.Option(False, "--all", help="Fetch all sources"),
):
    """Fetch archived/closed bids with bid results."""
    from app.tasks import fetch_source, fetch_all_archives
    db = _get_db()
    try:
        if all_sources:
            results = fetch_all_archives(db, fixture=fixture)
            for r in results:
                typer.echo(f"  {r}")
        elif source:
            result = fetch_source(db, source, fixture=fixture, archives=True)
            typer.echo(result)
        else:
            typer.echo("Specify --source <key> or --all")
            raise typer.Exit(1)
    finally:
        db.close()


@app.command("update-planholders")
def update_planholders(
    source: str = typer.Option(..., "--source", help="Source key"),
):
    """Update planholder lists for open projects from a source."""
    typer.echo(f"Planholder update for '{source}' — not yet implemented for this source.")


@app.command("update-results")
def update_results(
    source: str = typer.Option(..., "--source", help="Source key"),
):
    """Update bid results for projects from a source."""
    typer.echo(f"Results update for '{source}' — not yet implemented for this source.")


@app.command("calculate-analytics")
def calculate_analytics():
    """Calculate bid analytics for all projects with results."""
    from app.analytics import calculate_all_analytics
    db = _get_db()
    try:
        count = calculate_all_analytics(db)
        typer.echo(f"Analytics calculated for {count} project(s).")
    finally:
        db.close()


@app.command("export-csv")
def export_csv_cmd(output_dir: str = typer.Option(".", "--output", help="Output directory")):
    """Export all tables to CSV files."""
    from app.tasks import export_csv
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    db = _get_db()
    try:
        exports = export_csv(db)
        for name, content in exports.items():
            path = out / f"{name}.csv"
            path.write_text(content, encoding="utf-8")
            typer.echo(f"  Wrote {path}")
        typer.echo(f"Export complete — {len(exports)} files.")
    finally:
        db.close()


@app.command("run-server")
def run_server(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
):
    """Start the FastAPI web server."""
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
