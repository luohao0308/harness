"""
Validation API endpoints - Story 2.1 & 2.2

Provides endpoints for:
- System requirements validation (POST /api/onboarding/validate/system)
- Configuration validation (POST /api/onboarding/validate/config)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import ValidationResponse
from app.db.session import get_db_session
from app.services.validation_service import ValidationService

router = APIRouter(prefix="/onboarding/validate", tags=["validation"])
DbSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/system",
    response_model=ValidationResponse,
    summary="Validate system requirements",
)
def validate_system(session: DbSession) -> dict:
    """
    Validate system requirements (Story 2.1).

    Checks:
    - Python version (≥ 3.11)
    - Node.js version (≥ 20)
    - Disk space (≥ 10 GB free)
    - Memory (≥ 4 GB available)

    Returns validation results with pass/warn/fail status for each check.
    """
    service = ValidationService(session)
    results = service.validate_all_system()

    return {
        "checks": results,
        "summary": _generate_summary(results),
    }


@router.post(
    "/config",
    response_model=ValidationResponse,
    summary="Validate configuration",
)
def validate_config(session: DbSession) -> dict:
    """
    Validate configuration (Story 2.2).

    Checks:
    - Required secrets (JWT_SECRET, ENCRYPTION_KEY)
    - Database connectivity
    - API_BASE_URL accessibility
    - CORS configuration
    - Model provider API keys (optional)

    Returns validation results with pass/warn/fail status for each check.
    """
    service = ValidationService(session)
    results = service.validate_all_config()

    return {
        "checks": results,
        "summary": _generate_summary(results),
    }


def _generate_summary(results: list[dict]) -> dict:
    """
    Generate summary statistics from validation results.

    Args:
        results: List of validation check results

    Returns:
        Summary with counts of pass/warn/fail and overall status
    """
    pass_count = sum(1 for r in results if r["status"] == "pass")
    warn_count = sum(1 for r in results if r["status"] == "warn")
    fail_count = sum(1 for r in results if r["status"] == "fail")

    # Overall status: fail if any fail, warn if any warn, otherwise pass
    if fail_count > 0:
        overall_status = "fail"
    elif warn_count > 0:
        overall_status = "warn"
    else:
        overall_status = "pass"

    return {
        "total": len(results),
        "pass": pass_count,
        "warn": warn_count,
        "fail": fail_count,
        "status": overall_status,
    }
