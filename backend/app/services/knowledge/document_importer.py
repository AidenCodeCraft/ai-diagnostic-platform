"""Multi-format document importer — Markdown, plain text, future PDF/Word."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


class DocumentImporter:
    """Parse uploaded documents into structured content chunks.

    Supported formats: .md, .txt (MVP)
    Future: .pdf, .docx via additional parsers
    """

    MAX_CHUNK_SIZE = 2000  # characters per chunk

    def parse_file(self, path: str | Path) -> Dict[str, Any]:
        """Parse a file and return structured content with metadata."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = file_path.suffix.lower()
        if suffix == ".md":
            return self._parse_markdown(file_path)
        elif suffix in (".txt", ".log", ".text"):
            return self._parse_plain(file_path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    def parse_text(self, content: str, filename: str = "unknown") -> Dict[str, Any]:
        """Parse raw text content into structured form."""
        ext = Path(filename).suffix.lower()
        title = Path(filename).stem

        if ext == ".md":
            return self._parse_markdown_text(content, title)
        return {
            "title": title,
            "content": content,
            "format": "text",
            "chunks": self._chunk_text(content),
        }

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def _parse_markdown(self, path: Path) -> Dict[str, Any]:
        content = path.read_text(encoding="utf-8", errors="ignore")
        title = path.stem
        return self._parse_markdown_text(content, title)

    def _parse_markdown_text(self, content: str, title: str) -> Dict[str, Any]:
        # Extract title from first # heading if present
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and len(stripped) > 2:
                title = stripped[2:].strip()
                break

        return {
            "title": title,
            "content": content,
            "format": "markdown",
            "chunks": self._chunk_text(content),
        }

    # ------------------------------------------------------------------
    # Plain text
    # ------------------------------------------------------------------

    def _parse_plain(self, path: Path) -> Dict[str, Any]:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return {
            "title": path.stem,
            "content": content,
            "format": "text",
            "chunks": self._chunk_text(content),
        }

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into paragraphs, keeping chunks under MAX_CHUNK_SIZE."""
        chunks: List[str] = []
        current = ""
        for line in text.splitlines():
            if len(current) + len(line) > self.MAX_CHUNK_SIZE and current:
                chunks.append(current.strip())
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            chunks.append(current.strip())
        return chunks if chunks else [text[: self.MAX_CHUNK_SIZE]]
