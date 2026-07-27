"""Function Calling API — enable tool-assisted conversations."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.chat.function_calling_agent import FunctionCallingAgent


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/function-calling", tags=["function-calling"])


@router.post("/chat")
def chat_with_tools(
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
):
    """Send a message and let LLM decide whether to call tools.

    Request body:
        messages: List[Dict[str, str]] - conversation history
        model: str (optional) - LLM model name
        max_iterations: int (optional) - max tool call loops

    Response:
        content: str - final reply
        tool_calls: List[Dict] - tool call history
        iterations: int - number of loops
    """
    messages = body.get("messages", [])
    model = body.get("model", "deepseek")
    max_iterations = body.get("max_iterations", 5)

    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    try:
        agent = FunctionCallingAgent(db, provider_name=model)
        result = agent.chat_with_tools(messages, max_iterations=max_iterations)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tools")
def list_available_tools(db: Session = Depends(get_db_session)):
    """List all available tools and their specifications."""
    agent = FunctionCallingAgent(db)
    return {
        "tools": agent.tools.list_specs(),
        "count": len(agent.tools.tool_names),
    }
