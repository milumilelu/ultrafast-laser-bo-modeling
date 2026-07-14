from __future__ import annotations

from pathlib import Path

from ultrafast_shared.config.loader import get_database_path
from ultrafast_shared.db.session import get_connection as get_connection


def get_engine(db_path: str | Path | None = None):
    from sqlalchemy import create_engine

    path = Path(db_path) if db_path else get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", future=True)


class _LazySessionFactory:
    def __call__(self, *args, **kwargs):
        from sqlalchemy.orm import sessionmaker

        return sessionmaker(autocommit=False, autoflush=False)(*args, **kwargs)


SessionLocal = _LazySessionFactory()
