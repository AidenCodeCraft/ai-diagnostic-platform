"""Vector Search API — Milvus 向量搜索接口。

支持：
- 语义向量搜索
- 混合搜索（向量 + 关键词）
- 文档索引管理
- 索引状态查询
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.services.knowledge.vector_service import VectorService, get_vector_service
from app.services.knowledge.document_indexer import DocumentIndexer
from app.services.knowledge.embedding_service import EmbeddingService
from app.services.knowledge.knowledge_service import KnowledgeService

router = APIRouter(prefix="/vector", tags=["vector-search"])


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


# ── Request/Response Models ────────────────────────────────

class VectorSearchRequest(BaseModel):
    """向量搜索请求。"""
    query: str = Field(..., description="搜索查询文本", min_length=1)
    top_k: int = Field(5, ge=1, le=50, description="返回结果数")
    use_hybrid: bool = Field(True, description="是否使用混合搜索（默认：向量+关键词）")


class VectorSearchResult(BaseModel):
    """单个搜索结果。"""
    id: int
    title: Optional[str] = None
    score: float
    source: str = "vector"
    category: Optional[str] = None
    snippet: Optional[str] = None


class VectorSearchResponse(BaseModel):
    """向量搜索响应。"""
    query: str
    strategy: str  # "hybrid" / "vector_only" / "keyword_only"
    total_hits: int
    results: List[VectorSearchResult]


class IndexDocumentRequest(BaseModel):
    """文档索引请求。"""
    doc_id: int = Field(..., description="文档 ID")
    content: Optional[str] = Field(None, description="文档内容（None 时从 DB 读取）")
    force: bool = Field(False, description="是否强制重新索引")


class IndexDocumentResponse(BaseModel):
    """文档索引响应。"""
    doc_id: int
    chunks_indexed: int
    success: bool
    message: str


class IndexStatusResponse(BaseModel):
    """索引状态响应。"""
    vector_service_available: bool
    milvus_enabled: bool
    total_indexed: int
    total_failed: int
    last_index_time: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────

@router.post("/search", response_model=VectorSearchResponse)
def vector_search(
    body: VectorSearchRequest,
    db: Session = Depends(get_db_session),
):
    """语义向量搜索 — 优先使用 Milvus，不可用时回退到关键词。

    请求示例：
    ```json
    {
      "query": "USB timeout 超时问题",
      "top_k": 5,
      "use_hybrid": true
    }
    ```
    """
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    try:
        if body.use_hybrid:
            # 混合搜索
            indexer = DocumentIndexer(db)
            hybrid_result = indexer.search_with_hybrid(
                body.query,
                vector_top_k=body.top_k,
                keyword_top_k=body.top_k,
            )

            # 转换为标准格式
            results = []
            for item in hybrid_result.get("fused", [])[:body.top_k]:
                doc_id: int | None = item.get("id")
                title: str | None = None
                category: str | None = None

                if doc_id is not None:
                    try:
                        doc = KnowledgeService(db).get(doc_id)
                        title = str(doc.title) if doc.title is not None else None  # type: ignore[arg-type]
                        category = str(doc.category) if doc.category is not None else None  # type: ignore[arg-type]
                    except Exception:
                        pass

                results.append(VectorSearchResult(
                    id=doc_id or 0,
                    title=title,
                    score=item.get("score", 0),
                    source=item.get("source", "keyword"),
                    category=category,
                    snippet=item.get("snippet", ""),
                ))

            return VectorSearchResponse(
                query=body.query,
                strategy=hybrid_result.get("strategy", "hybrid"),
                total_hits=hybrid_result.get("total_hits", 0),
                results=results,
            )

        else:
            # 纯向量搜索
            vector_svc = get_vector_service()
            vector_results = vector_svc.search(body.query, top_k=body.top_k)

            results = []
            for vr in vector_results:
                v_doc_id: int | None = vr.get("id")
                v_title: str | None = None
                if v_doc_id is not None:
                    try:
                        doc = KnowledgeService(db).get(v_doc_id)
                        v_title = str(doc.title) if doc.title is not None else None  # type: ignore[arg-type]
                    except Exception:
                        pass

                results.append(VectorSearchResult(
                    id=v_doc_id or 0,
                    title=v_title,
                    score=vr.get("score", 0),
                    source="vector",
                    snippet=vr.get("content", "")[:200],
                ))

            return VectorSearchResponse(
                query=body.query,
                strategy="vector_only",
                total_hits=len(results),
                results=results,
            )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {exc}")


@router.post("/index", response_model=IndexDocumentResponse)
def index_document(
    body: IndexDocumentRequest,
    db: Session = Depends(get_db_session),
):
    """索引单个文档到向量数据库。

    请求示例：
    ```json
    {
      "doc_id": 1,
      "content": "USB超时问题的排查方法...",
      "force": false
    }
    ```
    """
    try:
        indexer = DocumentIndexer(db)
        chunks = indexer.index_document(
            body.doc_id,
            content=body.content,
            force=body.force,
        )

        return IndexDocumentResponse(
            doc_id=body.doc_id,
            chunks_indexed=chunks,
            success=chunks > 0,
            message=f"Indexed {chunks} chunks for document {body.doc_id}",
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}")


@router.post("/reindex-all")
def reindex_all(db: Session = Depends(get_db_session)):
    """全量重建索引 — 索引所有活跃文档。"""
    try:
        indexer = DocumentIndexer(db)
        stats = indexer.reindex_all()
        return {"success": True, **stats}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {exc}")


@router.delete("/index/{doc_id}")
def delete_index(doc_id: int, db: Session = Depends(get_db_session)):
    """删除文档的向量索引。"""
    try:
        indexer = DocumentIndexer(db)
        success = indexer.delete_from_index(doc_id)

        if success:
            return {"success": True, "message": f"Deleted index for doc {doc_id}"}
        else:
            return {"success": False, "message": f"Failed to delete index for doc {doc_id}"}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete index failed: {exc}")


@router.get("/status", response_model=IndexStatusResponse)
def index_status(db: Session = Depends(get_db_session)):
    """查询向量索引状态。"""
    try:
        vector_svc = get_vector_service()
        indexer = DocumentIndexer(db)

        stats = indexer.stats
        return IndexStatusResponse(
            vector_service_available=vector_svc.available,
            milvus_enabled=vector_svc.available,
            total_indexed=stats.get("total_indexed", 0),
            total_failed=stats.get("total_failed", 0),
            last_index_time=stats.get("last_index_time"),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Status check failed: {exc}")


@router.get("/health")
def vector_health():
    """向量服务健康检查。"""
    try:
        vector_svc = get_vector_service()
        collection_info = vector_svc.collection_info

        return {
            "milvus_available": vector_svc.available,
            "milvus_enabled": vector_svc._connected,
            "collection": collection_info,
            "embedding_provider": EmbeddingService().provider_name,
        }
    except Exception as exc:
        return {
            "milvus_available": False,
            "milvus_enabled": False,
            "error": str(exc),
        }


@router.post("/embed")
def test_embedding(body: Dict[str, Any]):
    """测试嵌入生成（用于调试/验证）。"""
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    embedding_svc = EmbeddingService()
    embedding = embedding_svc.embed(text)

    return {
        "text": text[:100],
        "dimension": len(embedding),
        "embedding_preview": embedding[:10],  # 前10维预览
        "norm": sum(v ** 2 for v in embedding) ** 0.5,
    }
