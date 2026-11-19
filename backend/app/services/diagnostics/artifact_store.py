"""预处理中间产物存储（P2 产物迁对象存储）。

为什么必须迁：worker 是多进程/多机部署，`parse` 在 A 机写本地文件、
`template` 可能在 B 机读——本地目录根本读不到，链路会静默断在中间。

布局（对象存储 / 本地一致）：
  ingest/{log_id}/normalized_{chunk}.jsonl.gz
  ingest/{log_id}/templates.json
  ingest/{log_id}/compressed.bundle.jsonl.gz

对象存储不可用时自动回退本地 `UPLOAD_DIR/_ingest/{log_id}/`，
与改造前行为一致（单机开发不需要 MinIO 也能跑通）。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.diagnostics.log_storage import LogStorage

logger = get_logger(__name__)

LOCAL_DIRNAME = "_ingest"


class ArtifactStore:
    def __init__(self, storage: Optional[LogStorage] = None, local_root: Optional[str] = None):
        self.storage = storage or LogStorage()
        root = local_root or str(getattr(settings, "UPLOAD_DIR", "data/raw"))
        self.local_root = Path(root) / LOCAL_DIRNAME

    @staticmethod
    def prefix(log_id: int) -> str:
        return f"ingest/{int(log_id)}/"

    def _local_path(self, log_id: int, name: str) -> Path:
        return self.local_root / str(int(log_id)) / name

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    def put(self, log_id: int, name: str, data: bytes) -> str:
        """写入产物；返回引用（minio://... 或本地绝对路径）。"""
        key = f"{self.prefix(log_id)}{name}"
        reference = self.storage.put_bytes(key=key, data=data)
        if reference:
            return reference

        path = self._local_path(log_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def put_text(self, log_id: int, name: str, text: str) -> str:
        return self.put(log_id, name, text.encode("utf-8"))

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def get(self, log_id: int, name: str) -> Optional[bytes]:
        data = self.storage.get_bytes(f"{self.prefix(log_id)}{name}")
        if data is not None:
            return data
        path = self._local_path(log_id, name)
        if path.exists():
            return path.read_bytes()
        return None

    def list(self, log_id: int) -> List[str]:
        """产物名列表（对象存储 ∪ 本地，去重排序）。"""
        names = set()
        prefix = self.prefix(log_id)
        for key in self.storage.list_keys(prefix):
            if key.startswith(prefix):
                names.add(key[len(prefix):])

        directory = self.local_root / str(int(log_id))
        if directory.exists():
            names.update(item.name for item in directory.iterdir() if item.is_file())
        return sorted(names)

    def normalized_names(self, log_id: int) -> List[str]:
        return [name for name in self.list(log_id) if name.startswith("normalized_")]

    def delete_local(self, log_id: int) -> None:
        """清理本地产物（对象存储侧按 ILM 处理，不在这里删）。"""
        directory = self.local_root / str(int(log_id))
        if not directory.exists():
            return
        for item in directory.iterdir():
            if item.is_file():
                item.unlink(missing_ok=True)
        try:
            directory.rmdir()
        except OSError:
            logger.debug("[artifact] 本地目录非空，跳过删除: %s", directory)
