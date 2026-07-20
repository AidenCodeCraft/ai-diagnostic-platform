from __future__ import annotations

from typing import Dict, List, Optional

from app.services.parser.base import BaseParser, ParsedEvent
from app.services.parser.generic_parser import GenericParser
from app.services.parser.kernel_parser import KernelLogParser
from app.services.parser.linux_parser import LinuxSyslogParser


class ParserRegistry:
    """Registry and auto-detection hub for log parsers.

    Tries specialized parsers first, falls back to GenericParser.
    """

    def __init__(self) -> None:
        self._parsers: Dict[str, BaseParser] = {}
        self._ordered: List[BaseParser] = []
        self._generic = GenericParser()
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(KernelLogParser())
        self.register(LinuxSyslogParser())
        # GenericParser is always the fallback, not registered in ordered list

    def register(self, parser: BaseParser) -> None:
        """Register a parser. Later registrations take priority."""
        self._parsers[parser.source_type] = parser
        self._ordered.append(parser)

    def get_by_source(self, source_type: str) -> Optional[BaseParser]:
        return self._parsers.get(source_type)

    def detect(self, line: str) -> BaseParser:
        """Return the first parser that can handle this line."""
        for parser in self._ordered:
            if parser.can_parse(line):
                return parser
        return self._generic

    def parse_line(self, line: str, force_source: Optional[str] = None) -> ParsedEvent:
        """Parse a single line with either forced or auto-detected parser."""
        if force_source:
            parser = self.get_by_source(force_source)
            if parser is None:
                raise ValueError(f"No parser registered for source type: {force_source}")
            return parser.parse_line(line)
        return self.detect(line).parse_line(line)

    def parse_text(
        self,
        text: str,
        force_source: Optional[str] = None,
    ) -> List[ParsedEvent]:
        """Parse multi-line text, auto-detecting parser per line unless forced."""
        events: List[ParsedEvent] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(self.parse_line(stripped, force_source))
            except Exception:
                events.append(BaseParser._fallback_event(stripped))
        return events

    def parse_lines(
        self,
        lines: List[str],
        force_source: Optional[str] = None,
    ) -> List[ParsedEvent]:
        """Parse a list of pre-stripped lines."""
        return self.parse_text("\n".join(lines), force_source)

    @property
    def registered_sources(self) -> List[str]:
        return list(self._parsers.keys())
