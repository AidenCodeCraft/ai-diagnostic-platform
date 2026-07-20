from __future__ import annotations

from pathlib import Path
from typing import Generator, List, Optional


class LogReader:
    """Read log files efficiently, with support for streaming large files.

    Handles line-by-line and chunked reading, encoding detection,
    and basic size checks.
    """

    DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB

    def __init__(self, encoding: str = "utf-8") -> None:
        self.encoding = encoding

    def read_all(self, path: str | Path) -> str:
        """Read entire file content at once (suitable for small logs)."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Log file not found: {path}")
        return file_path.read_text(encoding=self.encoding, errors="ignore")

    def read_lines(self, path: str | Path) -> List[str]:
        """Read all lines, stripping trailing newlines and skipping empty ones."""
        content = self.read_all(path)
        return [line.strip() for line in content.splitlines() if line.strip()]

    def stream_lines(self, path: str | Path) -> Generator[str, None, None]:
        """Generator that yields one stripped line at a time (memory-efficient)."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Log file not found: {path}")
        with file_path.open("r", encoding=self.encoding, errors="ignore") as fh:
            for line in fh:
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
