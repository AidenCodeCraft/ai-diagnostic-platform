"""Chat session service — persistence + AI chat with diagnostic agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import ChatSession, ChatMessage
from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
from app.services.chat.context_manager import ContextManager
from app.services.chat.title_generator import should_generate_title
from app.services.knowledge.provider_registry import ProviderRegistry


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.context_manager = ContextManager()

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

    def update_session(self, session_id: int, title: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> ChatSession:
        s = self.get_session(session_id)
        if title is not None:
            setattr(s, 'title', title)
        if context is not None:
            existing = s.context or {}
            existing.update(context)
            setattr(s, 'context', existing)
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

    def add_message(
        self, session_id: int, role: str, content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        thinking: Optional[Dict[str, Any]] = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id, role=role, content=content,
            sources=sources, thinking=thinking,
        )
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

    def _resolve_log_analysis(
        self, session_id: int, log_analysis: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Resolve log_analysis: use passed-in value, else fall back to session context."""
        if log_analysis:
            return log_analysis
        session = self.get_session(session_id)
        ctx = session.context or {}
        return ctx.get("last_analysis")

    def _build_messages(self, session_id: int) -> List[Dict[str, str]]:
        history = self.get_messages(session_id)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": DiagnosticChatAgent.SYSTEM_BASE}
        ]
        
        # 构建完整历史消息
        history_messages = []
        for m in history:
            history_messages.append({"role": m.role, "content": m.content})
        
        # 应用上下文管理（自动摘要压缩）
        if self.context_manager.should_compress(history_messages):
            history_messages = self.context_manager.manage_context(
                history_messages,
                DiagnosticChatAgent.SYSTEM_BASE
            )
        
        messages.extend(history_messages)
        return messages

    def _auto_title(self, session_id: int, content: str = "") -> None:
        """智能生成对话标题（基于 LLM 而非简单截取）。"""
        session = self.get_session(session_id)
        messages = self.get_messages(session_id)
        
        session_title_raw: Optional[str] = session.title  # type: ignore[assignment]
        if not should_generate_title(session_title_raw, len(messages)):
            return
        
        try:
            # 构建消息历史供标题生成使用
            history_messages = []
            for m in messages:
                history_messages.append({"role": m.role, "content": m.content})
            
            # 使用同步方式生成标题
            provider_name_raw = str(session.model or "deepseek")
            title = self._generate_title_sync(
                history_messages,
                provider_name=provider_name_raw
            )
            
            setattr(session, 'title', title)
            self.db.commit()
        except Exception:
            # 失败回退：使用简单截取
            current_title: Optional[str] = session.title  # type: ignore[assignment]
            if not current_title or current_title == "新对话":
                title = content[:30].strip()
                if len(content) > 30:
                    title += "…"
                setattr(session, 'title', title)
                self.db.commit()

    def _generate_title_sync(
        self,
        messages: List[Dict[str, str]],
        provider_name: str,
    ) -> str:
        """同步版本的标题生成。"""
        from app.services.chat.title_generator import generate_title_prompt
        
        if not messages:
            return "新对话"
        
        # 至少要有一条用户消息
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return "新对话"
        
        # 如果只有一条消息，直接使用前 20 字
        if len(messages) == 1:
            first_content = messages[0].get("content", "")[:20].strip()
            return first_content if first_content else "新对话"
        
        try:
            # 构建 prompt
            prompt = generate_title_prompt(messages)
            
            # 调用 LLM
            provider = self._get_provider(provider_name)
            title = provider.chat([{"role": "user", "content": prompt}])
            
            # 清理标题
            title = title.strip().replace('"', '').replace("'", '').replace('：', '').replace(':', '')
            
            # 限制长度
            if len(title) > 30:
                title = title[:30]
            
            # 如果生成失败，回退到简单截取
            if not title or len(title) < 3:
                first_user = user_messages[0].get("content", "")[:20].strip()
                return first_user if first_user else "新对话"
            
            return title
            
        except Exception:
            # 失败回退：使用第一条用户消息的前 20 字
            first_user = user_messages[0].get("content", "")[:20].strip()
            return first_user if first_user else "新对话"

    def send_message(
        self,
        session_id: int,
        content: str,
        model: Optional[str] = None,
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a user message and get an AI reply (non-streaming, with diagnostic context)."""
        session = self.get_session(session_id)
        provider_name = str(model or session.model or "mock")
        self.add_message(session_id, "user", content)
        messages = self._build_messages(session_id)

        # Resolve log_analysis from session context if not explicitly provided
        resolved_analysis = self._resolve_log_analysis(session_id, log_analysis)
        # Persist to session context for multi-turn inheritance
        if log_analysis:
            self.update_session(session_id, context={"last_analysis": log_analysis})

        # Enrich with diagnostic context
        agent = DiagnosticChatAgent(self.db, provider_name)
        messages = agent.enrich_messages(session_id, content, messages, resolved_analysis)

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
        """Stream AI reply with diagnostic context injection.

        log_analysis: if provided, persists to session context for multi-turn inheritance.
        Subsequent messages in the same session will auto-inherit via session.context.last_analysis.
        """
        session = self.get_session(session_id)
        provider_name = str(model or session.model or "mock")
        # 用户消息由前端 saveMessage 统一持久化，后端不再重复保存
        messages = self._build_messages(session_id)

        # Resolve log_analysis: passed-in value takes priority, else fall back to session context
        resolved_analysis = self._resolve_log_analysis(session_id, log_analysis)
        # Persist to session context so subsequent messages auto-inherit
        if log_analysis:
            self.update_session(session_id, context={"last_analysis": log_analysis})

        # Enrich with diagnostic context (knowledge search + analysis)
        agent = DiagnosticChatAgent(self.db, provider_name)
        messages = agent.enrich_messages(session_id, content, messages, resolved_analysis)
        if agent.references:
            yield f"data: {json.dumps({'sources': agent.references}, ensure_ascii=False)}\n\n"

        full_reply = ""
        try:
            provider = self._get_provider(provider_name)
            for chunk in provider.chat_stream(messages):
                if isinstance(chunk, dict):
                    reasoning = chunk.get("reasoning", "")
                    if reasoning:
                        yield f"data: {json.dumps({'reasoning': reasoning}, ensure_ascii=False)}\n\n"
                    continue
                full_reply += chunk
                yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            full_reply = f"[AI 服务暂时不可用: {e}]"
            yield f"data: {json.dumps({'token': full_reply})}\n\n"

        self._auto_title(session_id, content)
        # 注意：assistant 消息由前端 saveMessage 统一持久化（含 thinking/sources），
        # 后端不再重复保存，避免 message 重复。
        yield f"data: {json.dumps({'done': True, 'model': provider_name})}\n\n"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # 模块级单例 ProviderRegistry（避免每次调用重新读取 system_config.json）
    _provider_registry: ProviderRegistry | None = None

    @classmethod
    def _get_provider(cls, name: str):
        if cls._provider_registry is None:
            cls._provider_registry = ProviderRegistry()
        return cls._provider_registry.get_provider(name)
