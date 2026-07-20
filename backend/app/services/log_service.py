import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.log import Log


class LogService:
    """Service for managing log file uploads and metadata."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_log(
        self,
        file: UploadFile,
        project_id: Optional[int] = None,
        upload_user_id: Optional[int] = None,
        device: Optional[str] = None,
        version: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Log:
        """Persist an uploaded log file and create a database record."""
        upload_dir = self._resolve_upload_dir()
        upload_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(file.filename or "upload.log").name
        destination = self._unique_destination(upload_dir, filename)

        bytes_written = 0
        with destination.open("wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                buffer.write(chunk)
                bytes_written += len(chunk)

        log = Log(
            filename=filename,
            file_path=str(destination),
            size=bytes_written,
            status="uploaded",
            project_id=project_id,
            upload_user_id=upload_user_id,
            device=device,
            version=version,
            description=description,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_logs(self) -> List[Log]:
        return self.db.query(Log).order_by(Log.created_at.desc()).all()

    def get_log(self, log_id: int) -> Optional[Log]:
        return self.db.query(Log).filter(Log.id == log_id).first()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_log(self, log_id: int, updates: Dict[str, Any]) -> Log:
        log = self._get_or_raise(log_id)

        if "status" in updates:
            new_status = updates["status"]
            if not log.can_transition_to(new_status):
                raise ValueError(
                    f"Invalid status transition: {log.status} -> {new_status}"
                )
            log.status = new_status

        for field in ("project_id", "device", "version", "description"):
            if field in updates and updates[field] is not None:
                setattr(log, field, updates[field])

        self.db.commit()
        self.db.refresh(log)
        return log

    def update_status(self, log_id: int, status: str) -> Log:
        return self.update_log(log_id, {"status": status})

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_log(self, log_id: int) -> None:
        log = self._get_or_raise(log_id)
        self._remove_file(log.file_path)
        self.db.delete(log)
        self.db.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_or_raise(self, log_id: int) -> Log:
        log = self.get_log(log_id)
        if not log:
            raise ValueError("log not found")
        return log

    def _resolve_upload_dir(self) -> Path:
        upload_dir = Path(settings.UPLOAD_DIR)
        if not upload_dir.is_absolute():
            upload_dir = Path(__file__).resolve().parents[3] / upload_dir
        return upload_dir

    @staticmethod
    def _unique_destination(upload_dir: Path, filename: str) -> Path:
        destination = upload_dir / filename
        counter = 1
        while destination.exists():
            stem, suffix = os.path.splitext(filename)
            destination = upload_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        return destination

    @staticmethod
    def _remove_file(file_path: str) -> None:
        path = Path(file_path)
        if path.exists():
            path.unlink()
