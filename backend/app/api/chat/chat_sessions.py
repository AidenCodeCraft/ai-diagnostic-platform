"""Chat Session API — multi-turn conversation management.

所有会话按登录用户隔离：会话归属以 JWT 解析出的用户为准，
请求体/查询参数中的 user_id 一律忽略，跨用户访问按 404（不泄露存在性）处理。
"""

from __future__ import annotations
import logging
import traceback
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_auth
from app.services import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat-sessions", tags=["chat-sessions"])


@router.post("", status_code=201)
def create_session(
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    # 会话归属以 token 解析出的用户为准，忽略 body 中的 user_id
    return ChatService(db).create_session(
        title=body.get("title"), user_id=user_id,
        log_id=body.get("log_id"), model=body.get("model"),
        project_id=body.get("project_id"),
    )


@router.get("")
def list_sessions(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    # 只返回当前用户自己的会话
    return ChatService(db).list_sessions(
        user_id=user_id, page=max(1, page), page_size=max(1, min(100, page_size)),
    )


@router.get("/{session_id}")
def get_session(
    session_id: int,
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    try:
        return ChatService(db).get_session(session_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc


@router.put("/{session_id}")
def update_session(
    session_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    try:
        return ChatService(db).update_session(
            session_id,
            title=body.get("title"),
            is_pinned=body.get("is_pinned"),
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    try:
        ChatService(db).delete_session(session_id, user_id=user_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc


# Messages
@router.post("/{session_id}/messages", status_code=201)
def add_message(
    session_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    try:
        return ChatService(db).add_message(
            session_id, role=body["role"], content=body["content"],
            sources=body.get("sources"), thinking=body.get("thinking"),
            versions=body.get("versions"), active_version=body.get("active_version"),
            image_ids=body.get("image_ids"),
            status=body.get("status") or "ok",
            error_message=body.get("error_message"),
            analysis_id=body.get("analysis_id"),
            log_id=body.get("log_id"),
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc


@router.put("/{session_id}/messages/{message_id}")
def update_message(
    session_id: int,
    message_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    try:
        return ChatService(db).update_message(
            session_id, message_id, fields=body, user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/messages")
def get_messages(
    session_id: int,
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    try:
        return ChatService(db).get_messages(session_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc


@router.get("/{session_id}/analysis")
def get_session_analysis(
    session_id: int,
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    """返回会话最近一次附件分析任务，供刷新后恢复轮询/重试。

    优先用会话绑定的 log_id；老会话没有 log_id 时回退到最后一条带
    analysis_id 的消息。
    """
    from app.models import Analysis, ChatMessage

    try:
        session = ChatService(db).get_session(session_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    analysis = None
    log_id = session.log_id
    if log_id:
        analysis = (
            db.query(Analysis)
            .filter(Analysis.log_id == log_id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .first()
        )
    if analysis is None:
        last = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.analysis_id.isnot(None),
            )
            .order_by(ChatMessage.id.desc())
            .first()
        )
        if last is not None and last.analysis_id:
            analysis = db.query(Analysis).filter(
                Analysis.id == last.analysis_id,
            ).first()

    if analysis is None:
        return {"analysis": None}

    return {
        "analysis": {
            "id": analysis.id,
            "log_id": analysis.log_id,
            "status": analysis.status,
            "error_message": analysis.error_message,
            "summary": analysis.summary,
            "model": analysis.model,
            "created_at": analysis.created_at,
            "updated_at": analysis.updated_at,
        },
    }


def _bind_images(db: Session, body: Dict[str, Any], session_id: int, user_id: int) -> None:
    """把本次提问附带的截图绑定到会话（上传时可能还没有会话）。"""
    image_ids = body.get("image_ids") or []
    if not image_ids:
        # 兜底：前端先 saveMessage 再流式。若客户端漏传 image_ids，
        # 从本会话最后一条用户消息里取，避免截图证据悄悄丢失（2026-11-27）。
        from app.models import ChatMessage

        last_user_message = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id, ChatMessage.role == "user")
            .order_by(ChatMessage.id.desc())
            .first()
        )
        image_ids = list(getattr(last_user_message, "image_ids", None) or [])
    if not image_ids:
        return
    try:
        from app.services.vision.image_service import ChatImageService

        ChatImageService(db).bind_to_session(
            [int(value) for value in image_ids], session_id, user_id,
        )
    except Exception:  # noqa: BLE001 - 绑定失败不影响提问，但必须可观测
        logger.warning(
            "[chat] bind image ids failed: session=%s ids=%s", session_id, image_ids,
            exc_info=True,
        )


# AI Chat
@router.post("/{session_id}/chat")
def chat(
    session_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    """Send a message and get an AI reply (non-streaming).

    Optional body fields:
        log_analysis: dict with summary/root_cause/confidence/next_steps from log analysis
    """
    from app.services.system.concurrency import chat_gate
    from app.services.system.system_config import get_system_config

    limit = int(get_system_config().get("max_online_users", 0) or 0)
    if not chat_gate.acquire(limit):
        raise HTTPException(
            status_code=429,
            detail=f"当前同时在线人数已达上限（{limit}），请稍后再试",
        )
    try:
        _bind_images(db, body, session_id, user_id)
        return ChatService(db).send_message(
            session_id=session_id,
            content=body["content"],
            model=body.get("model"),
            log_analysis=body.get("log_analysis"),
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    finally:
        chat_gate.release()


@router.post("/{session_id}/stream")
def chat_stream(
    session_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    """Stream AI reply via SSE with diagnostic context injection."""
    # 归属校验必须在流开始前完成（校验失败直接 404，而不是 SSE error 事件）
    try:
        ChatService(db).get_session(session_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    _bind_images(db, body, session_id, user_id)

    def generate():
        # Send an initial heartbeat immediately. Without this, Nginx/Vite may
        # close the chunked response before the potentially slow
        # enrichment/knowledge-retrieval phase has produced its first token.
        yield 'data: {"status":"start"}\n\n'

        from app.services.system.concurrency import chat_gate
        from app.services.system.system_config import get_system_config

        limit = int(get_system_config().get("max_online_users", 0) or 0)
        if not chat_gate.acquire(limit):
            import json
            yield f"data: {json.dumps({'error': f'当前同时在线人数已达上限（{limit}），请稍后再试'}, ensure_ascii=False)}\n\n"
            return
        try:
            yield from ChatService(db).send_message_stream(
                session_id=session_id,
                content=body["content"],
                model=body.get("model"),
                log_analysis=body.get("log_analysis"),
                user_id=user_id,
            )
        except ValueError as e:
            # 会话不存在等可恢复错误 → 通过 SSE 返回错误
            logger.warning("[chat_stream] session_id=%s ValueError: %s", session_id, e)
            import json
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except GeneratorExit:
            # 客户端断开连接，正常情况，不记录为错误
            logger.debug("[chat_stream] session_id=%s client disconnected (GeneratorExit)", session_id)
        except Exception as e:
            logger.error(
                "[chat_stream] session_id=%s unhandled exception: %s\n%s",
                session_id, e, traceback.format_exc(),
            )
            import json
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
        finally:
            chat_gate.release()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.put("/{session_id}/messages/{message_id}/feedback")
def update_message_feedback(
    session_id: int,
    message_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    """Update message feedback: { "feedback": "like" | "dislike" | null }"""
    from app.models.chat.chat_session import ChatMessage

    try:
        ChatService(db).get_session(session_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc

    msg = db.query(ChatMessage).filter(
        ChatMessage.id == message_id,
        ChatMessage.session_id == session_id,
    ).first()
    if not msg:
        raise HTTPException(status_code=404, detail="消息不存在")

    fb = body.get("feedback")
    if fb not in ("like", "dislike", None, ""):
        raise HTTPException(status_code=400, detail="feedback 必须为 like / dislike / null")

    msg.feedback = fb or None  # type: ignore[assignment]
    db.commit()
    return {"ok": True, "feedback": msg.feedback}


@router.post("/{session_id}/messages/{message_id}/resolve")
def resolve_message(
    session_id: int,
    message_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
    user_id: int = Depends(require_auth),
):
    """用户确认「已解决/未解决」。已解决时触发自进化蒸馏（生成待审核候选）。"""
    resolved = bool(body.get("resolved"))
    if not resolved:
        return {"ok": True, "resolved": False, "candidate_profile_id": None}

    try:
        session = ChatService(db).get_session(session_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    from app.services.knowledge.distiller import KnowledgeDistiller

    try:
        profile = KnowledgeDistiller(db).distill_for_message(
            session_id, message_id, model=session.model,
        )
    except Exception as exc:
        logger.error("[resolve_message] session=%s message=%s distill failed: %s",
                     session_id, message_id, exc)
        raise HTTPException(status_code=500, detail=f"蒸馏失败: {exc}") from exc

    return {
        "ok": True,
        "resolved": True,
        "candidate_profile_id": profile.id if profile else None,
    }
