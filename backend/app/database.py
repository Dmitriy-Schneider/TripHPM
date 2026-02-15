"""
Настройка базы данных
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings
import logging

# Создаем engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Создаем SessionLocal класс
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()


def get_db():
    """Dependency для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_sqlite_schema():
    """Добавить отсутствующие колонки в SQLite без миграций."""
    if "sqlite" not in settings.DATABASE_URL:
        return

    logger = logging.getLogger(__name__)

    try:
        with engine.begin() as conn:
            # Миграции для таблицы trips
            trips_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(trips)")).fetchall()
            }

            migrations = []
            if "prikaz_date" not in trips_cols:
                migrations.append("ALTER TABLE trips ADD COLUMN prikaz_date DATE")
            if "sz_date" not in trips_cols:
                migrations.append("ALTER TABLE trips ADD COLUMN sz_date DATE")
            if "ao_date" not in trips_cols:
                migrations.append("ALTER TABLE trips ADD COLUMN ao_date DATE")
            if "pre_trip_docs_generated" not in trips_cols:
                migrations.append(
                    "ALTER TABLE trips ADD COLUMN pre_trip_docs_generated BOOLEAN DEFAULT 0"
                )
            if "post_trip_docs_generated" not in trips_cols:
                migrations.append(
                    "ALTER TABLE trips ADD COLUMN post_trip_docs_generated BOOLEAN DEFAULT 0"
                )

            # Миграции для таблицы receipts
            receipts_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(receipts)")).fetchall()
            }

            if "document_type" not in receipts_cols:
                migrations.append(
                    "ALTER TABLE receipts ADD COLUMN document_type VARCHAR DEFAULT 'fiscal'"
                )
            if "requires_amount" not in receipts_cols:
                migrations.append(
                    "ALTER TABLE receipts ADD COLUMN requires_amount BOOLEAN DEFAULT 1"
                )

            # Миграции для таблицы users
            users_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
            }

            if "signature_path" not in users_cols:
                migrations.append(
                    "ALTER TABLE users ADD COLUMN signature_path VARCHAR"
                )

            for stmt in migrations:
                conn.execute(text(stmt))
                logger.info("[DB] Applied schema migration: %s", stmt)
    except Exception as exc:
        logger.error("[DB] Failed to ensure SQLite schema: %s", exc, exc_info=True)
