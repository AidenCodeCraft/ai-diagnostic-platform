from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.schemas.log import LogResponse
from app.services.log_service import LogService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("/upload", response_model=LogResponse)
def upload_log(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(default=None),
    device: Optional[str] = Form(default=None),
    version: Optional[str] = Form(default=None),
    description: Optional[str] = Form(default=None),
    db: Session = Depends(get_db_session),
) -> LogResponse:
    """Upload a log file and persist the metadata in the database."""
    service = LogService(db)
    log = service.upload_log(
        file=file,
        project_id=project_id,
        device=device,
        version=version,
        description=description,
    )
    return LogResponse(
        id=log.id,
        log_id=log.id,
        filename=log.filename,
        file_path=log.file_path,
        status=log.status,
        project_id=log.project_id,
        device=log.device,
        version=log.version,
        description=log.description,
        created_at=log.created_at,
    )


@router.get("", response_model=List[LogResponse])
def list_logs(db: Session = Depends(get_db_session)) -> List[LogResponse]:
    """List uploaded logs."""
    logs = LogService(db).list_logs()
    return [
        LogResponse(
            id=log.id,
            log_id=log.id,
            filename=log.filename,
            file_path=log.file_path,
            status=log.status,
            project_id=log.project_id,
            device=log.device,
            version=log.version,
            description=log.description,
            created_at=log.created_at,
        )
        for log in logs
    ]
