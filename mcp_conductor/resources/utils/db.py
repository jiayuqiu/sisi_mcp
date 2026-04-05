from pathlib import Path

from sqlalchemy import Engine, create_engine

DB_PATH = Path("./data/sisi.sqlite")

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine for sisi.sqlite."""
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{DB_PATH.absolute()}")
    return _engine
