from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.models import Log
from app.schemas import LogResponse, LogUpdate
from app.services import LogService
from app.services.diagnostics.log_service import LogUploadError


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/logs", tags=["logs"])


# ------------------------------------------------------------------
# Upload
# ------------------------------------------------------------------


@router.post("/upload", response_model=LogResponse)
def upload_log(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(default=None),
    upload_user_id: Optional[int] = Form(default=None),
    device: Optional[str] = Form(default=None),
    version: Optional[str] = Form(default=None),
    description: Optional[str] = Form(default=None),
    db: Session = Depends(get_db_session),
) -> Log:
    """Upload a log file and persist the metadata in the database."""
    try:
        return LogService(db).upload_log(
            file=file,
            project_id=project_id,
            upload_user_id=upload_user_id,
            device=device,
            version=version,
            description=description,
        )
    except LogUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------


@router.get("", response_model=List[LogResponse])
def list_logs(
    project_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> List[Log]:
    """List uploaded logs (optionally filtered by project)."""
    return LogService(db).list_logs(project_id=project_id)


@router.get("/{log_id}", response_model=LogResponse)
def get_log(log_id: int, db: Session = Depends(get_db_session)) -> Log:
    """Retrieve a single log's metadata by ID."""
    log = LogService(db).get_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="log not found")
    return log


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------


@router.put("/{log_id}", response_model=LogResponse)
def update_log(
    log_id: int,
    body: LogUpdate,
    db: Session = Depends(get_db_session),
) -> Log:
    """Update log metadata or transition its status."""
    try:
        updates = body.model_dump(exclude_unset=True)
        return LogService(db).update_log(log_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


@router.delete("/{log_id}", status_code=204)
def delete_log(log_id: int, db: Session = Depends(get_db_session)):
    """Delete a log record and remove its file from storage."""
    try:
        LogService(db).delete_log(log_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
