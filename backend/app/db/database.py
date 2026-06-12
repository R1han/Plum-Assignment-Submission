from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    settings = get_settings()
    return create_engine(
        url or settings.database_url,
        connect_args={"check_same_thread": False}
        if (url or settings.database_url).startswith("sqlite") else {},
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db():
    from app.db import models  # noqa: F401 — register tables

    Base.metadata.create_all(engine)
