from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL



# Database Engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)


# Database Session
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# Retrieval worker sessions: every SQL statement is capped so a hung query
# can't hold a Celery worker past the request deadline.
retrieval_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={
        "options": f"-c statement_timeout={settings.RETRIEVAL_DB_STATEMENT_TIMEOUT_MS}"
    },
)

RetrievalSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=retrieval_engine,
)


# Base Model
class Base(DeclarativeBase):
    pass


# Database Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()