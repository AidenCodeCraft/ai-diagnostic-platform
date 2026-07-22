"""Chat Session API — multi-turn conversation management."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services import ChatService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/chat-sessions", tags=["chat-sessions"])


@router.post("", status_code=201)
def create_session(body: Dict[str, Any], db: Session = Depends(get_db_session)):
    return ChatService(db).create_session(
        title=body.get("title"), user_id=body.get("user_id"),
        log_id=body.get("log_id"), model=body.get("model"),
    )


@router.get("")
def list_sessions(user_id: Optional[int] = Query(default=None), page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db_session)):
    return ChatService(db).list_sessions(user_id=user_id, page=page, page_size=page_size)


@router.get("/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db_session)):
    try:
        return ChatService(db).get_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{session_id}")
def update_session(session_id: int, body: Dict[str, Any], db: Session = Depends(get_db_session)):
    try:
        return ChatService(db).update_session(session_id, title=body.get("title"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: int, db: Session = Depends(get_db_session)):
    try:
        ChatService(db).delete_session(session_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Messages
@router.post("/{session_id}/messages", status_code=201)
def add_message(session_id: int, body: Dict[str, Any], db: Session = Depends(get_db_session)):
    return ChatService(db).add_message(session_id, role=body["role"], content=body["content"])


@router.get("/{session_id}/messages")
def get_messages(session_id: int, db: Session = Depends(get_db_session)):
    return ChatService(db).get_messages(session_id)


# AI Chat
@router.post("/{session_id}/chat")
def chat(
    session_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
):
    """Send a message and get an AI reply (non-streaming).

    Optional body fields:
        log_analysis: dict with summary/root_cause/confidence/next_steps from log analysis
    """
    try:
        return ChatService(db).send_message(
            session_id=session_id,
            content=body["content"],
            model=body.get("model"),
            log_analysis=body.get("log_analysis"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/stream")
def chat_stream(
    session_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
):
    """Stream AI reply via SSE with diagnostic context injection."""
    try:

        def generate():
            yield from ChatService(db).send_message_stream(
                session_id=session_id,
                content=body["content"],
                model=body.get("model"),
                log_analysis=body.get("log_analysis"),
            )

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
