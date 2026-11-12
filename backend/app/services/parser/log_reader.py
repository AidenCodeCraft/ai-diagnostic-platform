"""Log reader — 编码探测、大文件限行读取、压缩包解压。"""

from __future__ import annotations

import gzip
import zipfile
from pathlib import Path
from typing import Generator, List, Optional, Tuple

# 编码探测候选（按命中概率排序）
_ENCODING_CANDIDATES = ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "utf-16")

_ARCHIVE_SUFFIXES = {".zip", ".gz"}
_TEXT_SUFFIXES = {".log", ".txt", ".out", ".trace", ".dmesg", ".json", ".csv"}


class LogReader:
    """Read log files efficiently, with encoding detection and large-file caps."""

    DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB
    DEFAULT_MAX_LINES = 200_000

    def __init__(self, encoding: Optional[str] = None) -> None:
        self.encoding = encoding  # None 表示自动探测

    # ------------------------------------------------------------------
    # Encoding
    # ------------------------------------------------------------------

    def detect_encoding(self, path: str | Path) -> str:
        """探测文件编码（BOM → utf-8 → gb18030 → big5 → utf-16）。"""
        if self.encoding:
            return self.encoding
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Log file not found: {path}")
        raw = file_path.read_bytes()[:65536]

        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return "utf-16"

        for encoding in _ENCODING_CANDIDATES:
            try:
                raw.decode(encoding)
                return encoding
            except UnicodeDecodeError:
                continue
        return "utf-8"

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_all(self, path: str | Path, max_chars: Optional[int] = None) -> str:
        """Read entire file content at once (suitable for small logs)."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Log file not found: {path}")
        text = file_path.read_text(encoding=self.detect_encoding(file_path), errors="ignore")
        if max_chars and len(text) > max_chars:
            text = text[:max_chars]
        return text

    def read_all_capped(
        self,
        path: str | Path,
        max_lines: Optional[int] = None,
    ) -> Tuple[str, bool]:
        """读取文件，最多 max_lines 行（防大文件爆内存）。

        Returns:
            (text, truncated)
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Log file not found: {path}")

        limit = max_lines or self.DEFAULT_MAX_LINES
        encoding = self.detect_encoding(file_path)
        lines: List[str] = []
        truncated = False
        with file_path.open("r", encoding=encoding, errors="ignore") as handle:
            for index, line in enumerate(handle):
                if index >= limit:
                    truncated = True
                    break
                lines.append(line)
        return "".join(lines), truncated

    def read_lines(self, path: str | Path) -> List[str]:
        """Read all lines, stripping trailing newlines and skipping empty ones."""
        content = self.read_all(path)
        return [line.strip() for line in content.splitlines() if line.strip()]

    def stream_lines(self, path: str | Path) -> Generator[str, None, None]:
        """Generator that yields one stripped line at a time (memory-efficient)."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Log file not found: {path}")
        encoding = self.detect_encoding(file_path)
        with file_path.open("r", encoding=encoding, errors="ignore") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    yield stripped

    def read_size_mb(self, path: str | Path) -> float:
        """Return file size in megabytes."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Log file not found: {path}")
        return file_path.stat().st_size / (1024 * 1024)

    def is_large(self, path: str | Path, threshold_mb: int = 10) -> bool:
        """Return True if the file exceeds the given size threshold."""
        return self.read_size_mb(path) > threshold_mb

    # ------------------------------------------------------------------
    # Archives（zip / gz）
    # ------------------------------------------------------------------

    @staticmethod
    def is_archive(path: str | Path) -> bool:
        return Path(path).suffix.lower() in _ARCHIVE_SUFFIXES

    @classmethod
    def extract_archive(cls, path: str | Path) -> Optional[Tuple[Path, str]]:
        """解压 zip/gz 到同目录，返回 (解压文件路径, 建议文件名)。

        非压缩包返回 None；空压缩包抛 ValueError。
        """
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix not in _ARCHIVE_SUFFIXES:
            return None

        if suffix == ".gz":
            target = file_path.with_suffix("")
            if target == file_path:
                target = file_path.with_name(file_path.name + ".log")
            with gzip.open(file_path, "rb") as source, target.open("wb") as dest:
                dest.write(source.read())
            return target, target.name

        with zipfile.ZipFile(file_path) as archive:
            candidates = [item for item in archive.infolist() if not item.is_dir()]
            if not candidates:
                raise ValueError("压缩包为空")
            preferred = [
                item for item in candidates
                if Path(item.filename).suffix.lower() in _TEXT_SUFFIXES
            ]
            chosen = (preferred or candidates)[0]
            target = file_path.with_name(f"{file_path.stem}_{Path(chosen.filename).name}")
            target.write_bytes(archive.read(chosen))
            return target, Path(chosen.filename).name
