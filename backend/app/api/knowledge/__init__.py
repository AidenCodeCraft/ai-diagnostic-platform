"""Knowledge Base API — CRUD and search for knowledge documents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import session as session_module
from app.schemas import (
    KnowledgeCreate,
    KnowledgeResponse,
    KnowledgeUpdate,
    KnowledgeListResponse,
    KnowledgeSearchResult,
    KnowledgeTreeResponse,
    KnowledgeImageResponse,
)
from app.services import (
    KnowledgeService,
    KnowledgeImageService,
    KnowledgeProfileService,
    KnowledgeFormatService,
    KnowledgeSectionService,
    KnowledgeDocumentMetaService,
    SectionParser,
)
from app.services.knowledge.polish_service import KnowledgePolishService
from app.services.knowledge.templates import list_templates


class PolishRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    doc_type: Optional[str] = None
    title: Optional[str] = None


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


def _ingest_images(db: Session, doc_id: int, content: str, base_dir=None) -> None:
    """抽取内容中的图片并入库，若 src 被重写则回写 content。"""
    new_content = KnowledgeImageService(db).process_document_images(
        doc_id, content, base_dir=base_dir,
    )
    if new_content != content:
        KnowledgeService(db).update(doc_id, {"content": new_content}, auto_index=False)


def _standardize(db: Session, doc_id: int) -> Dict[str, Any]:
    """入库强制规范化：内容规范化、分节/元信息落库、诊断剧本生成。"""
    doc = KnowledgeService(db).get(doc_id)
    fmt = KnowledgeFormatService().preview(doc.content or "", doc.doc_type, doc.title)

    doc.content = fmt["normalized_content"]
    doc.status = fmt["status_hint"]
    db.commit()
    db.refresh(doc)

    parsed = SectionParser.parse(doc.content or "", doc.doc_type)
    KnowledgeSectionService(db).replace(doc_id, parsed)
    KnowledgeDocumentMetaService(db).upsert(doc_id, {
        "template_key": doc.doc_type,
        "quality_score": fmt["quality_score"],
        "content_hash": KnowledgeDocumentMetaService.compute_hash(doc.content or ""),
        "features": fmt["features"],
    })

    merged = dict(fmt["profile_draft"])
    meaningful = any(
        merged.get(k) for k in ("symptom", "log_keywords", "log_patterns", "root_cause", "solution")
    )
    if meaningful:
        merged["status"] = "draft" if doc.status == "draft" else "active"
        merged["source"] = "template"
        KnowledgeProfileService(db).upsert(doc_id, merged)

    # 规范化后内容已变化，重新同步向量索引（Milvus 启用时）
    KnowledgeService(db).reindex(doc_id, doc.content or "")
    return fmt


def _doc_payload(db: Session, doc_id: int, fmt=None) -> Dict[str, Any]:
    """返回文档 + 校验结果（issues / quality_score / suggested_keywords）。"""
    doc = KnowledgeService(db).get(doc_id)
    payload = KnowledgeResponse.model_validate(doc).model_dump()
    if fmt is not None:
        payload["issues"] = fmt.get("issues", [])
        payload["quality_score"] = fmt.get("quality_score", 0.0)
        payload["suggested_keywords"] = fmt.get("suggested_keywords", [])
    return payload


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------


@router.post("", status_code=201)
def create_document(
    body: KnowledgeCreate,
    db: Session = Depends(get_db_session),
) -> Any:
    """创建知识条目：入库前强制规范化 + 校验（图片、分节、质量分、诊断剧本）。"""
    data = body.model_dump()
    content = data.get("content") or ""
    doc = KnowledgeService(db).create(data, auto_index=False)
    if content:
        _ingest_images(db, doc.id, content)
    if content and (doc.doc_type or "") != "folder":
        fmt = _standardize(db, doc.id)
        return _doc_payload(db, doc.id, fmt)
    return _doc_payload(db, doc.id)


@router.post("/upload", response_model=KnowledgeResponse, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(default=None),
    doc_type: str = Form(default="manual"),
    parent_id: Optional[int] = Form(default=None),
    db: Session = Depends(get_db_session),
) -> Any:
    """Upload a document file (.md, .txt) and import into knowledge base."""
    from pathlib import Path
    from tempfile import gettempdir
    from app.services import DocumentImporter

    tmp_path = Path(gettempdir()) / (file.filename or "upload")
    tmp_path.write_bytes(file.file.read())

    try:
        importer = DocumentImporter()
        result = importer.parse_file(tmp_path)
        content = result["content"] or ""
        doc = KnowledgeService(db).create({
            "title": result["title"],
            "content": content,
            "category": category,
            "doc_type": doc_type,
            "source": file.filename,
            "parent_id": parent_id,
        }, auto_index=False)
        if content:
            _ingest_images(db, doc.id, content, base_dir=tmp_path.parent)
        if content and (doc_type or "") != "folder":
            fmt = _standardize(db, doc.id)
            return _doc_payload(db, doc.id, fmt)
        return _doc_payload(db, doc.id)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------


@router.get("", response_model=KnowledgeListResponse)
def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    doc_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    parent_id: Optional[int] = Query(default=None),
    project_id: Optional[int] = Query(default=None),
    sort: str = Query(default="updated_desc", pattern="^(updated_asc|updated_desc)$"),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """List knowledge documents with optional filters and updated-time ordering."""
    return KnowledgeService(db).list(
        page=page,
        page_size=page_size,
        category=category,
        parent_id=parent_id,
        doc_type=doc_type,
        status=status,
        project_id=project_id,
        sort_order=sort,
    )


@router.post("/polish")
def polish_document(
    body: PolishRequest,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """AI 润色 + 模板规范化（LLM 不可用时自动回退规则整理）。"""
    return KnowledgePolishService(db).polish(
        body.content, body.doc_type, body.title or "",
    )


@router.get("/search")
def search_documents(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    project_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Search knowledge documents by keyword."""
    return KnowledgeService(db).search(
        query_text=q, page=page, page_size=page_size, project_id=project_id,
    )


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db_session),
) -> List[str]:
    """List all active document categories."""
    return KnowledgeService(db).list_categories()


@router.get("/tree", response_model=KnowledgeTreeResponse)
def get_tree(
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Get full knowledge base folder/document tree."""
    return {"tree": KnowledgeService(db).get_tree()}


# ------------------------------------------------------------------
# Images
# ------------------------------------------------------------------


@router.post("/images", response_model=KnowledgeImageResponse, status_code=201)
def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
) -> Any:
    """上传单张知识库图片（编辑器插入用），返回可访问 URL。"""
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="图片内容为空")
    max_bytes = int(settings.MAX_IMAGE_SIZE_MB) * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"图片过大（最大 {settings.MAX_IMAGE_SIZE_MB}MB）")
    return KnowledgeImageService(db).save_uploaded_image(
        data, file.filename or "image.png", file.content_type,
    )


@router.get("/images/{image_id}")
def get_image(
    image_id: int,
    db: Session = Depends(get_db_session),
) -> Response:
    """流式返回知识库图片字节（本地与 MinIO 统一入口）。"""
    try:
        data, mime = KnowledgeImageService(db).get_bytes(image_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="image not found")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="image data missing")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"image read failed: {exc}")
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/images/{image_id}/feedback", status_code=200)
def feedback_image(
    image_id: int,
    body: Dict[str, Any],
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """逐图反馈：标记「不相关」以优化后续图片关联。body: { "feedback": "irrelevant" }"""
    feedback = body.get("feedback")
    if feedback != "irrelevant":
        raise HTTPException(status_code=400, detail="feedback 必须为 irrelevant")
    try:
        KnowledgeImageService(db).record_feedback(image_id, feedback)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "image_id": image_id, "feedback": feedback}


@router.get("/templates")
def get_templates() -> Dict[str, Any]:
    """返回全部知识模板契约（章节与必填级别）。"""
    return {"templates": list_templates()}


@router.get("/{doc_id}/sections")
def get_sections(
    doc_id: int,
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """返回知识条目的分节（章节 + 行号范围），供预览/审核/定位。"""
    try:
        KnowledgeService(db).get(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows = KnowledgeSectionService(db).list(doc_id)
    return {"sections": [KnowledgeSectionService.to_dict(r) for r in rows]}


@router.post("/format/preview")
def format_preview(body: Dict[str, Any]) -> Dict[str, Any]:
    """不落库：规范化 + 校验，返回「提交后格式」预览。"""
    return KnowledgeFormatService().preview(
        content=body.get("content") or "",
        doc_type=body.get("doc_type"),
        title=body.get("title"),
    )


@router.get("/{doc_id}", response_model=KnowledgeResponse)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db_session),
) -> Any:
    """Get a single knowledge document by ID."""
    try:
        return KnowledgeService(db).get(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Update
# ------------------------------------------------------------------


@router.put("/{doc_id}")
def update_document(
    doc_id: int,
    body: KnowledgeUpdate,
    db: Session = Depends(get_db_session),
) -> Any:
    """更新知识条目：内容变更时强制重新规范化 + 校验。"""
    try:
        data = body.model_dump(exclude_unset=True)
        if data.get("content"):
            data["content"] = KnowledgeImageService(db).process_document_images(
                doc_id, data["content"],
            )
        doc = KnowledgeService(db).update(doc_id, data, auto_index=False)
        if (data.get("content") or data.get("doc_type")) and (doc.doc_type or "") != "folder":
            fmt = _standardize(db, doc_id)
            return _doc_payload(db, doc_id, fmt)
        return _doc_payload(db, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db_session),
):
    """Delete a knowledge document."""
    from sqlalchemy.exc import IntegrityError
    try:
        KnowledgeService(db).delete(doc_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Cannot delete: document has dependencies") from exc
