"""
Administrative inspection routes.

Implements Issue #21: [Telemetry & Observability] Implement Centralized Debug
Logging & Audit Ledger Pipeline.

Features:
- GET /api/admin/recent-errors: Inspect in-memory ring buffer of the last 50
  warning/error traces, protected by static bearer token (settings.ADMIN_TOKEN).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.logger import get_recent_errors

router = APIRouter(prefix="/api/admin", tags=["admin"])
bearer_scheme = HTTPBearer(auto_error=False)


async def verify_admin_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Validate that the incoming request contains a valid admin bearer token."""
    if not credentials or credentials.credentials != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/recent-errors", response_model=list[dict[str, Any]])
async def recent_errors(
    _: Annotated[None, Depends(verify_admin_token)],
) -> list[dict[str, Any]]:
    """
    Retrieve the last 50 warning/error records from the in-memory ring buffer.
    Requires Bearer token authentication matching settings.ADMIN_TOKEN.
    """
    return get_recent_errors()
