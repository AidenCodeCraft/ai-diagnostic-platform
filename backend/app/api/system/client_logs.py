"""Client log batch ingestion endpoint.

Accepts batches of frontend client-side logs (ERROR/WARN) and persists them
for monitoring, debugging, and audit purposes.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models import ClientLogEntry
from app.schemas import ClientLogBatchRequest


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/logs", tags=["logs"])


def _extract_user_id(request: Request, db: Session) -> Optional[int]:
    """Extract user ID from JWT token in request (best-effort)."""
    try:
        from app.services import AuthService

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return AuthService(db).verify_token(auth[7:])
    except Exception:
        pass
    return None


@router.post("/batch", status_code=201)
def ingest_client_logs(
    body: ClientLogBatchRequest,
    request: Request,
    db: Session = Depends(get_db_session),
):
    """Ingest a batch of client-side log entries.

    Accepts up to 200 log entries per request.  Each entry is validated
    and persisted individually for durability.
    """
    user_id = _extract_user_id(request, db)

    models = []
    for entry in body.entries:
        model = ClientLogEntry(
            id=entry.id,
            timestamp=entry.timestamp,
            level=entry.level,
            category=entry.category,
            message=entry.message,
            context=entry.context,
            tags=entry.tags,
            user_id=user_id,
        )
        models.append(model)

    try:
        db.add_all(models)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to persist logs: {str(exc)}") from exc

    return {"accepted": len(models)}
