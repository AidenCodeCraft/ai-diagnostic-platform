from typing import List, Dict

from fastapi import APIRouter, UploadFile, File, Form
from pathlib import Path

from app.services.parser_service import LogParserService

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
    return LogParserService().parse_file(temp_path)
