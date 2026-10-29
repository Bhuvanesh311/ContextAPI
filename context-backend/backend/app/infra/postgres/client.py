from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infra.postgres.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_DATABASE,
    POSTGRES_USERNAME,
    POSTGRES_PASSWORD,
)

from app.infra.postgres.constants import (
    DEFAULT_POOL_SIZE,
    DEFAULT_MAX_OVERFLOW,
    DEFAULT_POOL_TIMEOUT,
    DEFAULT_POOL_RECYCLE,
)


DATABASE_URL = (
    f"postgresql+psycopg://"
    f"{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}"
    f"/{POSTGRES_DATABASE}"
)


engine = create_engine(
    DATABASE_URL,
    pool_size=DEFAULT_POOL_SIZE,
    max_overflow=DEFAULT_MAX_OVERFLOW,
    pool_timeout=DEFAULT_POOL_TIMEOUT,
    pool_recycle=DEFAULT_POOL_RECYCLE,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)