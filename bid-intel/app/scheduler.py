"""APScheduler setup. Only starts when SCHEDULER_ENABLED=true."""
from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from app.config import settings

_scheduler: BackgroundScheduler | None = None


def _fetch_all_job():
    from app.db import SessionLocal
    from app.tasks import fetch_all_sources
    db = SessionLocal()
    try:
        fetch_all_sources(db, fixture=False)
    finally:
        db.close()


def _check_results_job():
    from app.db import SessionLocal
    from app.analytics import calculate_all_analytics
    db = SessionLocal()
    try:
        calculate_all_analytics(db)
    finally:
        db.close()


def _sheets_sync_job():
    from app.db import SessionLocal
    from app.sheets import sync_to_sheets
    db = SessionLocal()
    try:
        sync_to_sheets(db)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler()

    _scheduler.add_job(
        _fetch_all_job,
        IntervalTrigger(hours=settings.fetch_interval_hours),
        id="interval_fetch",
        replace_existing=True,
    )

    _scheduler.add_job(
        _check_results_job,
        IntervalTrigger(hours=settings.fetch_interval_hours, minutes=5),
        id="interval_results_check",
        replace_existing=True,
    )

    _scheduler.add_job(
        _sheets_sync_job,
        CronTrigger(
            day_of_week=settings.sheets_sync_day,
            hour=settings.sheets_sync_hour,
            minute=settings.sheets_sync_minute,
        ),
        id="weekly_sheets_sync",
        replace_existing=True,
    )

    _scheduler.start()
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
