"""Chat session service — persistence + AI chat with diagnostic agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.chat_session import ChatSession, ChatMessage
from app.services.diagnostic_chat_agent import DiagnosticChatAgent
from app.services.provider_registry import ProviderRegistry


class ChatService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(self, title: Optional[str] = None, user_id: Optional[int] = None, log_id: Optional[int] = None, model: Optional[str] = None) -> ChatSession:
        session = ChatSession(title=title, user_id=user_id, log_id=log_id, model=model or "mock")
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

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # AI Chat
    # ------------------------------------------------------------------

    def _build_messages(self, session_id: int) -> List[Dict[str, str]]:
        history = self.get_messages(session_id)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": DiagnosticChatAgent.SYSTEM_BASE}
        ]
        for m in history:
            messages.append({"role": m.role, "content": m.content})
        return messages

    def _auto_title(self, session_id: int, content: str):
        session = self.get_session(session_id)
        if not session.title or session.title == "新对话":
            title = content[:30].strip()
            if len(content) > 30:
                title += "…"
            session.title = title
            self.db.commit()

    def send_message(
        self,
        session_id: int,
        content: str,
        model: Optional[str] = None,
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a user message and get an AI reply (non-streaming, with diagnostic context)."""
        session = self.get_session(session_id)
        provider_name = model or session.model or "mock"
        self.add_message(session_id, "user", content)
        messages = self._build_messages(session_id)

        # Enrich with diagnostic context
        agent = DiagnosticChatAgent(self.db, provider_name)
        messages = agent.enrich_messages(session_id, content, messages, log_analysis)

        try:
            reply = self._get_provider(provider_name).chat(messages)
        except Exception as e:
            reply = f"[AI 服务暂时不可用: {e}]"

        self.add_message(session_id, "assistant", reply)
        self._auto_title(session_id, content)
        return {"reply": reply, "model": provider_name}

    def send_message_stream(
        self,
        session_id: int,
        content: str,
        model: Optional[str] = None,
        log_analysis: Optional[Dict[str, Any]] = None,
    ):
        """Stream AI reply with diagnostic context injection."""
        session = self.get_session(session_id)
        provider_name = model or session.model or "mock"
        self.add_message(session_id, "user", content)
        messages = self._build_messages(session_id)

        # Enrich with diagnostic context (knowledge search + analysis)
        agent = DiagnosticChatAgent(self.db, provider_name)
        messages = agent.enrich_messages(session_id, content, messages, log_analysis)

        full_reply = ""
        try:
            provider = self._get_provider(provider_name)
            for token in provider.chat_stream(messages):
                full_reply += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            full_reply = f"[AI 服务暂时不可用: {e}]"
            yield f"data: {json.dumps({'token': full_reply})}\n\n"

        self.add_message(session_id, "assistant", full_reply)
        self._auto_title(session_id, content)
        yield f"data: {json.dumps({'done': True, 'model': provider_name})}\n\n"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_provider(name: str):
        registry = ProviderRegistry()
        return registry.get_provider(name)
