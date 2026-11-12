import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models import Log, LogEvent
from app.services.diagnostics.log_storage import LogStorage
from app.services.parser.log_reader import LogReader

logger = get_logger(__name__)


class LogUploadError(ValueError):
    """日志上传校验失败（带 HTTP 状态码）。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


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

        max_bytes = max(1, int(settings.MAX_UPLOAD_MB)) * 1024 * 1024
        bytes_written = 0
        try:
            with destination.open("wb") as buffer:
                while chunk := file.file.read(1024 * 1024):
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise LogUploadError(
                            f"文件超过上传大小限制（{settings.MAX_UPLOAD_MB}MB）",
                            status_code=413,
                        )
                    buffer.write(chunk)

            self._reject_binary_if_needed(destination)

            stored_path = destination
            stored_name = filename
            extracted = LogReader.extract_archive(destination)
            if extracted:
                stored_path, stored_name = extracted
                destination.unlink(missing_ok=True)
                bytes_written = stored_path.stat().st_size
        except Exception:
            destination.unlink(missing_ok=True)
            raise

        # 保存到对象存储（MinIO 启用时）或保留本地路径
        file_reference = LogStorage().save(stored_path, stored_name)

        log = Log(
            filename=stored_name,
            file_path=file_reference,
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

        logger.info(
            "Log uploaded: id=%d file=%s size=%d bytes user=%s",
            log.id, filename, bytes_written, upload_user_id or "anon",
        )
        return log

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_logs(self, project_id: Optional[int] = None) -> List[Log]:
        query = self.db.query(Log)
        if project_id is not None:
            query = query.filter(Log.project_id == project_id)
        return query.order_by(Log.created_at.desc()).all()

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
        """删除日志：先清解析事件与元数据（同一 DB 事务），成功后再删对象/文件。

        注意（历史 P1 bug 修复）：`log_events.log_id` 外键没有 ON DELETE CASCADE
        （本次不改 schema/迁移），因此必须显式删除事件行，否则 `DELETE /logs/{id}`
        在已解析日志上会抛 `ForeignKeyViolation` → 500。

        删除顺序保证：DB 事务失败时对象不会被删（避免“对象已删、logs 记录悬空、
        日志不可再解析”的不一致）；对象删除失败仅记录告警、不阻断删除
        （DB 记录已删，残留对象可按前缀离线清理）。

        后续可选方案（未实施）：给 `log_events.log_id` 加 `ondelete="CASCADE"`
        + alembic 迁移，或在 DB 层用触发器清理。
        """
        log = self._get_or_raise(log_id)
        reference = str(log.file_path or "")

        # 1) DB：先删事件（外键引用方），再删日志记录，同一事务提交。
        self.db.query(LogEvent).filter(LogEvent.log_id == log_id).delete(
            synchronize_session=False
        )
        self.db.delete(log)
        self.db.commit()

        # 2) 存储：DB 事务成功后删除 MinIO 对象 / 本地文件；失败只告警不阻断。
        try:
            LogStorage().delete(reference)
        except Exception as exc:  # noqa: BLE001 - 清理失败不应让删除接口 500
            logger.warning(
                "[LogService] delete storage failed (log_id=%d, ref=%s): %s",
                log_id, reference, exc,
            )

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
    def _reject_binary_if_needed(path: Path) -> None:
        """非压缩包的二进制文件（含 NUL 字节）直接拒绝。"""
        if LogReader.is_archive(path):
            return
        head = path.read_bytes()[:8192]
        if b"\x00" in head:
            raise LogUploadError("不支持二进制文件，请上传文本日志或 .zip/.gz 压缩包", status_code=400)

    @staticmethod
    def _remove_file(file_path: str) -> None:
        path = Path(file_path)
        if path.exists():
            path.unlink()
