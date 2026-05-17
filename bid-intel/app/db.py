from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

_is_sqlite = "sqlite" in settings.database_url

if _is_sqlite:
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 — registers all models
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def _migrate_db():
    """Idempotently add new columns to existing tables."""
    from sqlalchemy import inspect, text

    new_cols = [
        ("projects", "bid_type", "VARCHAR(50)"),
        ("projects", "project_type", "VARCHAR(100)"),
        ("projects", "construction_manager", "VARCHAR(255)"),
        ("projects", "architect", "VARCHAR(255)"),
    ]
    inspector = inspect(engine)
    for table, col, col_type in new_cols:
        try:
            existing = {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            continue
        if col not in existing:
            with engine.connect() as conn:
                try:
                    if _is_sqlite:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                    else:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                    conn.commit()
                except Exception:
                    pass
