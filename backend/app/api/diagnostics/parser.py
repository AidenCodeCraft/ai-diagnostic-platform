from typing import Any, Dict, List

from fastapi import APIRouter, Form, Query, UploadFile, File
from pathlib import Path

from app.services import LogParserService

router = APIRouter(prefix="/parser", tags=["parser"])


@router.post("/parse")
def parse_log_text(text: str = Form(...)) -> List[Dict[str, object]]:
    """Parse a log text payload into structured events."""
    return LogParserService().parse_text(text)


@router.post("/parse-file")
def parse_log_file(file: UploadFile = File(...)) -> List[Dict[str, object]]:
    """Parse an uploaded log file into structured events."""
    temp_path = Path("/tmp") / file.filename
    temp_path.write_bytes(file.file.read())
    try:
        return LogParserService().parse_file(temp_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


@router.post("/parse-structured")
def parse_structured(
    text: str = Form(...),
    force_source: str = Query(default=""),
) -> Dict[str, Any]:
    """Parse text and return a structured ParseResult with statistics."""
    source = force_source.strip() or None
    service = LogParserService()
    events = service.registry.parse_text(text, force_source=source)
    from app.schemas import ParseResult
    return ParseResult.from_events(events, status="completed").model_dump()
