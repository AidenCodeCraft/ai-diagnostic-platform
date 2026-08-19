"""Multi-format document importer — Markdown, plain text, future PDF/Word."""

from __future__ import annotations

import re
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
    # Image extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_images(content: str) -> List[Dict[str, Any]]:
        """从 Markdown 内容中抽取图片引用及其章节/上下文元信息。

        支持语法：
          ![alt](src)
          ![alt](src "title")
          ![alt](<src>)

        Returns:
            [{"alt", "src", "anchor", "position", "context_text"}, ...]
        """
        images: List[Dict[str, Any]] = []
        if not content:
            return images

        # 先定位所有标题，用于给图片打「章节锚点」
        heading_re = re.compile(r"(?m)^(\#{1,6})\s+(.+?)\s*$")
        headings = [(m.start(), m.group(2).strip()) for m in heading_re.finditer(content)]

        # 图片语法：![alt](src "title")
        image_re = re.compile(r"!\[([^\]]*)\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+[\"']([^\"']*)[\"'])?\s*\)")

        position = 0
        for m in image_re.finditer(content):
            alt = (m.group(1) or "").strip()
            src = (m.group(2) or "").strip()
            title = (m.group(3) or "").strip()
            # 去掉 <...> 包裹
            if src.startswith("<") and src.endswith(">"):
                src = src[1:-1]

            # 最近的上方标题作为章节锚点
            anchor = ""
            for hs, ht in headings:
                if hs <= m.start():
                    anchor = ht
                else:
                    break

            start = max(0, m.start() - 120)
            end = min(len(content), m.end() + 120)
            position += 1
            images.append({
                "alt": alt or title or "",
                "src": src,
                "anchor": anchor,
                "position": position,
                "context_text": content[start:end],
            })

        return images

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
