"""Chat session service — persistence + AI chat with diagnostic agent."""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import ChatSession, ChatMessage
from app.services.chat.diagnostic_chat_agent import DiagnosticChatAgent
from app.services.chat.context_manager import ContextManager
from app.services.chat.title_generator import should_generate_title
from app.services.knowledge.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: Session, model: Optional[str] = None):
        self.db = db
        self.model = model
        self.context_manager = ContextManager(model=model)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self, title: Optional[str] = None, user_id: Optional[int] = None,
        log_id: Optional[int] = None, model: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> ChatSession:
        session = ChatSession(
            title=title, user_id=user_id, log_id=log_id,
            project_id=project_id, model=model or "mock",
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: int, user_id: Optional[int] = None) -> ChatSession:
        """读取会话；提供 user_id 时校验归属（非本人的会话按不存在处理）。"""
        query = self.db.query(ChatSession).filter(ChatSession.id == session_id)
        if user_id is not None:
            query = query.filter(ChatSession.user_id == user_id)
        s = query.first()
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

    def update_session(self, session_id: int, title: Optional[str] = None, context: Optional[Dict[str, Any]] = None, user_id: Optional[int] = None) -> ChatSession:
        s = self.get_session(session_id, user_id)
        if title is not None:
            setattr(s, 'title', title)
        if context is not None:
            existing = s.context or {}
            existing.update(context)
            setattr(s, 'context', existing)
        self.db.commit()
        self.db.refresh(s)
        return s

    def delete_session(self, session_id: int, user_id: Optional[int] = None) -> None:
        s = self.get_session(session_id, user_id)
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
        user_id: Optional[int] = None,
        versions: Optional[List[Dict[str, Any]]] = None,
        active_version: Optional[int] = None,
    ) -> ChatMessage:
        self.get_session(session_id, user_id)  # 归属校验
        msg = ChatMessage(
            session_id=session_id, role=role, content=content,
            sources=sources, thinking=thinking,
            versions=versions, active_version=active_version,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def update_message(
        self, session_id: int, message_id: int, fields: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> ChatMessage:
        """更新消息的可编辑字段（编辑重发：content / sources / thinking / versions / active_version）。"""
        self.get_session(session_id, user_id)  # 归属校验
        msg = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.id == message_id, ChatMessage.session_id == session_id)
            .first()
        )
        if not msg:
            raise ValueError("message not found")
        allowed = {"content", "sources", "thinking", "versions", "active_version"}
        for key, value in (fields or {}).items():
            if key in allowed and value is not None:
                setattr(msg, key, value)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_messages(self, session_id: int, user_id: Optional[int] = None) -> List[ChatMessage]:
        self.get_session(session_id, user_id)  # 归属校验
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
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a user message and get an AI reply (non-streaming, with diagnostic context)."""
        session = self.get_session(session_id, user_id)
        provider_name = str(model or session.model or "mock")
        self.add_message(session_id, "user", content, user_id=user_id)
        messages = self._build_messages(session_id)

        # Resolve log_analysis from session context if not explicitly provided
        resolved_analysis = self._resolve_log_analysis(session_id, log_analysis)
        # Persist to session context for multi-turn inheritance
        if log_analysis:
            self.update_session(session_id, context={"last_analysis": log_analysis})

        # Enrich with diagnostic context（按会话所属项目过滤知识）
        agent = DiagnosticChatAgent(
            self.db, provider_name, project_id=getattr(session, "project_id", None),
        )
        messages, direct_reply = agent.enrich_messages(session_id, content, messages, resolved_analysis)

        if direct_reply is not None:
            reply = direct_reply
        else:
            try:
                reply = self._get_provider(provider_name).chat(messages)
            except Exception as e:
                reply = f"[AI 服务暂时不可用: {e}]"

        self.add_message(session_id, "assistant", reply, user_id=user_id)
        self._auto_title(session_id, content)
        return {"reply": reply, "model": provider_name}

    def send_message_stream(
        self,
        session_id: int,
        content: str,
        model: Optional[str] = None,
        log_analysis: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ):
        """Stream AI reply with diagnostic context injection.

        log_analysis: if provided, persists to session context for multi-turn inheritance.
        Subsequent messages in the same session will auto-inherit via session.context.last_analysis.
        """
        session = self.get_session(session_id, user_id)
        provider_name = str(model or session.model or "mock")
        # 用户消息由前端 saveMessage 统一持久化，后端不再重复保存
        messages = self._build_messages(session_id)

        # Resolve log_analysis: passed-in value takes priority, else fall back to session context
        resolved_analysis = self._resolve_log_analysis(session_id, log_analysis)
        # Persist to session context so subsequent messages auto-inherit
        if log_analysis:
            self.update_session(session_id, context={"last_analysis": log_analysis})

        # Enrich with diagnostic context (knowledge search + analysis)
        try:
            agent = DiagnosticChatAgent(
                self.db, provider_name, project_id=getattr(session, "project_id", None),
            )
            messages, direct_reply = agent.enrich_messages(session_id, content, messages, resolved_analysis)
            if agent.references:
                yield f"data: {json.dumps({'sources': agent.references}, ensure_ascii=False)}\n\n"
            if getattr(agent, "clarification_questions", None):
                yield f"data: {json.dumps({'clarification': agent.clarification_questions}, ensure_ascii=False)}\n\n"

            # 如果 enrich_messages 已生成直接回复（如主动追问），直接流式输出，不调 LLM
            if direct_reply is not None:
                logger.debug(
                    "[send_message_stream] session_id=%s direct_reply from enrich_messages, skipping LLM",
                    session_id,
                )
                # 模拟流式输出：逐字符发送
                for char in direct_reply:
                    yield f"data: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
                try:
                    self._auto_title(session_id, content)
                except Exception as e:
                    logger.warning("[send_message_stream] session_id=%s auto_title failed: %s", session_id, e)
                yield f"data: {json.dumps({'done': True, 'model': provider_name})}\n\n"
                return
        except Exception as e:
            logger.error(
                "[send_message_stream] session_id=%s enrich_messages failed: %s\n%s",
                session_id, e, traceback.format_exc(),
            )
            yield f"data: {json.dumps({'error': f'知识检索异常: {e}'})}\n\n"
            return

        full_reply = ""
        stream_iter = None
        try:
            provider = self._get_provider(provider_name)
            stream_iter = provider.chat_stream(messages)
            for chunk in stream_iter:
                if isinstance(chunk, dict):
                    reasoning = chunk.get("reasoning", "")
                    if reasoning:
                        yield f"data: {json.dumps({'reasoning': reasoning}, ensure_ascii=False)}\n\n"
                    continue
                full_reply += chunk
                yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            # 客户端断开连接导致 generator 退出，正常流程
            logger.debug("[send_message_stream] session_id=%s GeneratorExit (client disconnected)", session_id)
            return
        except Exception as e:
            logger.error(
                "[send_message_stream] session_id=%s provider chat_stream failed: %s\n%s",
                session_id, e, traceback.format_exc(),
            )
            full_reply = f"[AI 服务暂时不可用: {e}]"
            yield f"data: {json.dumps({'token': full_reply})}\n\n"
        finally:
            # 客户端停止/断开时显式关闭上游 LLM 流（含 HTTP 连接），不依赖 GC
            if stream_iter is not None:
                close = getattr(stream_iter, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:  # noqa: BLE001 - 关闭失败不影响响应
                        pass

        try:
            self._auto_title(session_id, content)
        except Exception as e:
            logger.warning("[send_message_stream] session_id=%s auto_title failed: %s", session_id, e)

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
