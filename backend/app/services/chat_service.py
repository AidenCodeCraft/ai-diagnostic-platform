"""Chat session service — multi-turn conversation persistence."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession, ChatMessage


class ChatService:
    def __init__(self, db: Session):
        self.db = db

    def create_session(self, title: Optional[str] = None, user_id: Optional[int] = None, log_id: Optional[int] = None, model: Optional[str] = None) -> ChatSession:
        session = ChatSession(title=title, user_id=user_id, log_id=log_id, model=model)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: int) -> ChatSession:
        s = self.db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not s:
            raise ValueError("session not found")
        return s

    def list_sessions(self, user_id: Optional[int] = None, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        query = self.db.query(ChatSession)
        if user_id:
            query = query.filter(ChatSession.user_id == user_id)
        total = query.count()
        items = query.order_by(ChatSession.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def update_session(self, session_id: int, title: Optional[str] = None) -> ChatSession:
        s = self.get_session(session_id)
        if title is not None:
            s.title = title
        self.db.commit()
        self.db.refresh(s)
        return s

    def delete_session(self, session_id: int) -> None:
        s = self.get_session(session_id)
        self.db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
        self.db.delete(s)
        self.db.commit()

    # Messages
    def add_message(self, session_id: int, role: str, content: str) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=role, content=content)
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_messages(self, session_id: int) -> List[ChatMessage]:
        return self.db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at.asc()).all()
