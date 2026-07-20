"""Rule Engine API — manage diagnostic rules."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.services.rule_engine import RuleEngine

router = APIRouter(prefix="/rules", tags=["rules"])

_engine = RuleEngine()


@router.get("")
def list_rules() -> List[Dict[str, Any]]:
    return _engine.list_rules()


@router.post("", status_code=201)
def add_rule(body: Dict[str, str]):
    name = body.get("name", "").strip()
    match = body.get("match", "").strip()
    suggestion = body.get("suggestion", "").strip()
    if not name or not match or not suggestion:
        raise HTTPException(status_code=400, detail="name, match, suggestion are required")
    _engine.add_rule(name, match, suggestion)
    return {"status": "added", "name": name}


@router.delete("/{name}", status_code=204)
def remove_rule(name: str):
    if not _engine.remove_rule(name):
        raise HTTPException(status_code=404, detail="rule not found")
