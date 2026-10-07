from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url)
# expire_on_commit=False keeps objects readable after commit, so routers can return them as-is.
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    """One session per request, closed when the request ends."""
    with SessionLocal() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]
