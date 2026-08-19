"""Knowledge Base API — CRUD and search for knowledge documents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
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
from app.services import KnowledgeService, KnowledgeImageService


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
        KnowledgeService(db).update(doc_id, {"content": new_content})


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------


@router.post("", response_model=KnowledgeResponse, status_code=201)
def create_document(
    body: KnowledgeCreate,
    db: Session = Depends(get_db_session),
) -> Any:
    """Create a new knowledge document (含内容中图片的入库与 URL 重写)。"""
    data = body.model_dump()
    content = data.get("content") or ""
    doc = KnowledgeService(db).create(data)
    if content:
        _ingest_images(db, doc.id, content)
        doc = KnowledgeService(db).get(doc.id)
    return doc


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
    from app.services import DocumentImporter

    tmp_path = Path("/tmp") / (file.filename or "upload")
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
        })
        if content:
            _ingest_images(db, doc.id, content, base_dir=tmp_path.parent)
            doc = KnowledgeService(db).get(doc.id)
        return doc
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
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """List knowledge documents with optional filters."""
    return KnowledgeService(db).list(
        page=page,
        page_size=page_size,
        category=category,
        parent_id=parent_id,
        doc_type=doc_type,
        status=status,
    )


@router.get("/search")
def search_documents(
    q: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    """Search knowledge documents by keyword."""
    return KnowledgeService(db).search(query_text=q, page=page, page_size=page_size)


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


@router.put("/{doc_id}", response_model=KnowledgeResponse)
def update_document(
    doc_id: int,
    body: KnowledgeUpdate,
    db: Session = Depends(get_db_session),
) -> Any:
    """Update a knowledge document (含内容中图片的入库与 URL 重写)。"""
    try:
        data = body.model_dump(exclude_unset=True)
        if data.get("content"):
            data["content"] = KnowledgeImageService(db).process_document_images(
                doc_id, data["content"],
            )
        return KnowledgeService(db).update(doc_id, data)
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
