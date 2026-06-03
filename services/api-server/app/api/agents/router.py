"""Shared FastAPI router for Agent API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session

router = APIRouter(prefix="/agents", tags=["agents"])
DbSession = Annotated[Session, Depends(get_db_session)]
