"""Entry point for the Bid Intel CLI. Works on Windows PowerShell and Linux/macOS.

Usage:
    python manage.py init-db
    python manage.py list-sources
    python manage.py fetch --source mountain_view --fixture
    python manage.py fetch-archives --source mountain_view --fixture
    python manage.py calculate-analytics
    python manage.py export-csv
    python manage.py run-server
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.cli import app

if __name__ == "__main__":
    app()
