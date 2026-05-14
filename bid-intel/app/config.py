from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR}/bid_intel.db"
    debug: bool = False
    log_level: str = "INFO"

    host: str = "127.0.0.1"
    port: int = 8000

    scheduler_enabled: bool = False
    fetch_hour: int = 6
    fetch_minute: int = 0
    results_check_hour: int = 7
    results_check_minute: int = 0
    sheets_sync_day: str = "mon"
    sheets_sync_hour: int = 8
    sheets_sync_minute: int = 0

    google_sheets_credentials_file: str = ""
    google_sheets_spreadsheet_id: str = ""

    playwright_headless: bool = True

    autoseed_fixtures: bool = False
    autofetch_live: bool = False
    fetch_interval_hours: int = 6

    @property
    def fixtures_dir(self) -> Path:
        return BASE_DIR / "fixtures"

    @property
    def templates_dir(self) -> Path:
        return BASE_DIR / "app" / "templates"


settings = Settings()
