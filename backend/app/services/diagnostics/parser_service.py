from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.parser.registry import ParserRegistry
from app.services.parser.log_reader import LogReader

logger = get_logger(__name__)


class LogParserService:
    """Facade for log parsing — delegates to the pluggable parser engine.

    Maintains backwards compatibility with existing callers while routing
    through the new BaseParser / ParserRegistry infrastructure.
    """

    def __init__(self) -> None:
        self._registry = ParserRegistry()
        self._reader = LogReader()

    # ------------------------------------------------------------------
    # Public API (backward-compatible)
    # ------------------------------------------------------------------

    def parse_text(self, text: str, force_source: Optional[str] = None) -> List[Dict[str, object]]:
        events = self._registry.parse_text(text, force_source=force_source)
        return [e.to_dict() for e in events]

    def parse_file(self, path: str | Path, force_source: Optional[str] = None) -> List[Dict[str, object]]:
        text = self._read_capped(path)
        return self.parse_text(text, force_source=force_source)

    def parse_structured(self, path: str | Path, force_source: Optional[str] = None) -> list:
        """Parse a file and return raw ParsedEvent objects (new API)."""
        text = self._read_capped(path)
        return self._registry.parse_text(text, force_source=force_source)

    def _read_capped(self, path: str | Path) -> str:
        """读取日志文本（编码自动探测 + 大文件限行）。"""
        text, truncated = self._reader.read_all_capped(
            path, max_lines=settings.MAX_PARSE_LINES,
        )
        if truncated:
            logger.warning(
                "[ParserService] file %s exceeded %d lines; parsing truncated content",
                path, settings.MAX_PARSE_LINES,
            )
        return text

    def stream_parse(self, path: str | Path, force_source: Optional[str] = None) -> list:
        """Parse a large file line-by-line (memory-efficient)."""
        events = []
        for line in self._reader.stream_lines(path):
            events.append(self._registry.parse_line(line, force_source))
        return events

    # ------------------------------------------------------------------
    # Delegates
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ParserRegistry:
        return self._registry

    @property
    def reader(self) -> LogReader:
        return self._reader
