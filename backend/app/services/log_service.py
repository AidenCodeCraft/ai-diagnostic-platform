from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import init_db
from app.models.log import Log


class LogService:
    def __init__(self, db: Session):
        self.db = db

    def upload_log(
        self,
        file: UploadFile,
        project_id: Optional[int] = None,
        device: Optional[str] = None,
        version: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Log:
        """Persist an uploaded log file and create a database record."""
        init_db()

        upload_dir = Path(settings.UPLOAD_DIR)
        if not upload_dir.is_absolute():
            upload_dir = Path(__file__).resolve().parents[3] / upload_dir
        upload_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(file.filename or "upload.log").name
        destination = upload_dir / filename
        counter = 1
        while destination.exists():
            destination = upload_dir / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
            counter += 1

        with destination.open("wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                buffer.write(chunk)

        log = Log(
            filename=filename,
            file_path=str(destination),
            status="uploaded",
            project_id=project_id,
            device=device,
            version=version,
            description=description,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def list_logs(self) -> List[Log]:
        return self.db.query(Log).order_by(Log.created_at.desc()).all()
