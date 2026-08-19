"""Knowledge image service — 图片入库、与文档关联、URL 重写与字节读取。

职责：
  1. 编辑器单图上传（doc_id=None，随后在保存文档时回填关联）
  2. 处理文档内容中的图片：抽取 → 解析字节 → 上传存储 → 建记录 → 重写 src
  3. 图片查询与字节读取（供 API 流式返回）
"""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models import KnowledgeImage, KnowledgeImageFeedback
from app.services.knowledge.document_importer import DocumentImporter
from app.services.knowledge.image_storage import KnowledgeImageStorage

logger = get_logger(__name__)

# MIME → 扩展名（白名单）
MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
}
EXT_TO_MIME = {v: k for k, v in MIME_TO_EXT.items()}

# 本平台图片 URL：/api/v1/knowledge/images/{id}
_OWN_IMAGE_URL_RE = re.compile(r"^/api/v1/knowledge/images/(\d+)$")


class KnowledgeImageService:
    """知识库图片服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.storage = KnowledgeImageStorage()

    # ------------------------------------------------------------------
    # 上传单图（编辑器插入）
    # ------------------------------------------------------------------

    def save_uploaded_image(
        self,
        data: bytes,
        filename: str,
        content_type: Optional[str] = None,
    ) -> KnowledgeImage:
        if not data:
            raise ValueError("empty image data")
        content_type = content_type or self._guess_mime(filename, data)
        ext = MIME_TO_EXT.get(content_type, self._ext_from_filename(filename))
        sha = hashlib.sha256(data).hexdigest()
        storage_key = self._build_storage_key(sha, ext)
        self.storage.save(storage_key, data, content_type)

        img = KnowledgeImage(
            doc_id=None,
            storage_key=storage_key,
            caption=Path(filename).stem or "",
            mime_type=content_type,
            size_bytes=len(data),
            sha256=sha,
        )
        self.db.add(img)
        self.db.commit()
        self.db.refresh(img)
        logger.info("[ImageService] uploaded image id=%d size=%d", img.id, len(data))
        return img

    # ------------------------------------------------------------------
    # 处理文档内容中的图片（create / update / upload 共用）
    # ------------------------------------------------------------------

    def process_document_images(
        self,
        doc_id: int,
        content: str,
        base_dir: Optional[Path] = None,
    ) -> str:
        """抽取并入库内容中的图片，返回重写后的 content。

        处理规则：
          - `/api/v1/knowledge/images/{id}` → 已是本平台图片，回填 doc_id/章节关联，不改 src
          - `data:` / `http(s)://` / 本地相对路径 → 解析字节、存储、建记录、src 重写为本平台 URL
          - 无法解析（相对路径不存在、下载失败、超大）→ 保留原样并跳过
        """
        if not content:
            return content

        metas = DocumentImporter.extract_images(content)
        if not metas:
            return content

        mapping: Dict[str, str] = {}
        seen_sha: Dict[str, KnowledgeImage] = {}

        for meta in metas:
            src = meta["src"]
            stripped = src.strip()

            # 已是本平台图片 URL → 仅关联
            own = _OWN_IMAGE_URL_RE.match(stripped)
            if own:
                try:
                    img = self.get_image(int(own.group(1)))
                    self._associate(img, doc_id, meta)
                except Exception as exc:  # 记录不存在等
                    logger.warning("[ImageService] associate own image %s failed: %s", src, exc)
                continue

            # 外部/内联/相对图片 → 解析字节
            resolved = self._resolve_bytes(stripped, base_dir)
            if resolved is None:
                logger.info("[ImageService] skip unresolvable image src=%.60s", stripped)
                continue

            data, ctype, ext = resolved
            sha = hashlib.sha256(data).hexdigest()

            img = seen_sha.get(sha)
            if img is None:
                storage_key = self._build_storage_key(sha, ext)
                self.storage.save(storage_key, data, ctype)
                img = KnowledgeImage(
                    doc_id=doc_id,
                    storage_key=storage_key,
                    caption=meta.get("alt") or "",
                    anchor=meta.get("anchor") or "",
                    position=meta.get("position", 0),
                    context_text=meta.get("context_text"),
                    mime_type=ctype,
                    size_bytes=len(data),
                    sha256=sha,
                )
                self.db.add(img)
                self.db.flush()  # 获取自增 id 用于构造 URL
                seen_sha[sha] = img

            url = KnowledgeImageService.image_url(img.id)
            if url != src:
                mapping[src] = url

        self.db.commit()

        if mapping:
            content = self._rewrite_srcs(content, mapping)
        return content

    def _associate(self, img: KnowledgeImage, doc_id: int, meta: Dict[str, Any]) -> None:
        """把已有图片记录关联到文档并补充章节/顺序信息。"""
        if img.doc_id is None:
            img.doc_id = doc_id
        img.anchor = meta.get("anchor") or img.anchor
        img.position = meta.get("position", 0) or img.position
        img.context_text = meta.get("context_text") or img.context_text
        if not img.caption:
            img.caption = meta.get("alt") or ""

    # ------------------------------------------------------------------
    # 查询与读取
    # ------------------------------------------------------------------

    def get_image(self, image_id: int) -> KnowledgeImage:
        img = self.db.query(KnowledgeImage).filter(KnowledgeImage.id == image_id).first()
        if not img:
            raise ValueError("knowledge image not found")
        return img

    def list_images(self, doc_id: int) -> List[KnowledgeImage]:
        return (
            self.db.query(KnowledgeImage)
            .filter(KnowledgeImage.doc_id == doc_id)
            .order_by(KnowledgeImage.position.asc())
            .all()
        )

    def get_bytes(self, image_id: int) -> Tuple[bytes, str]:
        """返回 (bytes, mime_type)。图片缺失时抛 FileNotFoundError。"""
        img = self.get_image(image_id)
        data = self.storage.get_bytes(img.storage_key)
        return data, img.mime_type

    def match_images(
        self,
        doc_id: int,
        query: str = "",
        anchor: Optional[str] = None,
        top_k: int = 4,
    ) -> List[KnowledgeImage]:
        """为命中文档挑选关联图片（章节锚点为主，文本相似度为辅，位置兜底）。

        策略：
          1. 若存在与命中章节锚点匹配的图片 → 仅返回这些（强过滤，抑制图不对文）
          2. 否则按 query 与 caption/上下文 的文本相似度排序，取有信号的
          3. 无任何信号时回退到按文档内位置取前 top_k（文档级相关兜底）
        """
        images = self.list_images(doc_id)
        if not images:
            return []

        penalties = self._feedback_penalties(images)

        a = (anchor or "").strip()
        if a:
            matched = [img for img in images if self._anchor_matches(img.anchor, a)]
            if matched:
                return self._rank_with_penalty(matched, penalties, top_k)

        if query.strip():
            scored = [
                (self._text_relevance(img, query) - 0.3 * penalties.get(img.id, 0), img)
                for img in images
            ]
            scored.sort(key=lambda x: (-x[0], x[1].position or 0))
            if scored and scored[0][0] > 0:
                return [img for _, img in scored[:top_k]]

        return self._rank_with_penalty(images, penalties, top_k)

    def _rank_with_penalty(
        self,
        images: List[KnowledgeImage],
        penalties: Dict[int, int],
        top_k: int,
    ) -> List[KnowledgeImage]:
        """按负反馈降权：≥3 次不相关直接排除，其余按惩罚数 + 位置排序。"""
        kept = [img for img in images if penalties.get(img.id, 0) < 3]
        kept.sort(key=lambda i: (penalties.get(i.id, 0), i.position or 0))
        return kept[:top_k]

    def _feedback_penalties(self, images: List[KnowledgeImage]) -> Dict[int, int]:
        """统计每个图片的「不相关」反馈次数。"""
        if not images:
            return {}
        ids = [i.id for i in images]
        rows = (
            self.db.query(KnowledgeImageFeedback.image_id, func.count())
            .filter(
                KnowledgeImageFeedback.image_id.in_(ids),
                KnowledgeImageFeedback.feedback == "irrelevant",
            )
            .group_by(KnowledgeImageFeedback.image_id)
            .all()
        )
        return {int(r[0]): int(r[1]) for r in rows}

    def record_feedback(self, image_id: int, feedback: str) -> None:
        """记录逐图反馈（当前支持 'irrelevant'）。"""
        if feedback != "irrelevant":
            raise ValueError("unsupported feedback type")
        self.get_image(image_id)  # 校验图片存在
        row = KnowledgeImageFeedback(image_id=image_id, feedback=feedback)
        self.db.add(row)
        self.db.commit()
        logger.info("[ImageService] feedback recorded image=%d feedback=%s", image_id, feedback)

    @staticmethod
    def _anchor_matches(img_anchor: Optional[str], anchor: str) -> bool:
        ia = (img_anchor or "").strip()
        if not ia or not anchor:
            return False
        return ia == anchor or ia in anchor or anchor in ia

    @staticmethod
    def _text_relevance(img: KnowledgeImage, query: str) -> float:
        text = " ".join(
            x for x in [img.caption or "", img.anchor or "", img.context_text or ""] if x
        ).lower()
        if not text:
            return 0.0
        q = query.lower()
        cn_terms = [t for t in re.findall(r"[\u4e00-\u9fff]{2,}", q) if t]
        en_terms = [t for t in re.findall(r"[a-z0-9]{2,}", q) if t]
        terms = cn_terms + en_terms
        if not terms:
            return 0.0
        hits = sum(1 for t in terms if t in text)
        return hits / len(terms)

    @staticmethod
    def image_url(image_id: int) -> str:
        return f"/api/v1/knowledge/images/{image_id}"

    # ------------------------------------------------------------------
    # 字节解析
    # ------------------------------------------------------------------

    def _resolve_bytes(
        self, src: str, base_dir: Optional[Path],
    ) -> Optional[Tuple[bytes, str, str]]:
        """把图片 src 解析为 (bytes, mime, ext)。无法解析返回 None。"""
        s = src.strip()
        if s.startswith("data:"):
            return self._decode_data_uri(s)
        if s.startswith(("http://", "https://")):
            return self._download(s)
        if base_dir is not None:
            p = Path(s)
            if not p.is_absolute():
                p = base_dir / s
            if p.is_file():
                data = p.read_bytes()
                ctype = self._guess_mime(str(p), data)
                return data, ctype, MIME_TO_EXT.get(ctype, self._ext_from_filename(str(p)))
        return None

    def _decode_data_uri(self, src: str) -> Optional[Tuple[bytes, str, str]]:
        try:
            header, _, payload = src.partition(",")
            if not payload:
                return None
            meta = header[len("data:"):]
            is_b64 = ";base64" in meta
            mime = meta.split(";")[0].strip().lower() or "image/png"
            if mime not in MIME_TO_EXT:
                mime = "image/png"
            if is_b64:
                data = base64.b64decode(payload)
            else:
                data = unquote(payload).encode("utf-8")
            return data, mime, MIME_TO_EXT[mime]
        except Exception as exc:
            logger.warning("[ImageService] decode data uri failed: %s", exc)
            return None

    def _download(self, src: str) -> Optional[Tuple[bytes, str, str]]:
        try:
            max_bytes = int(getattr(settings, "MAX_IMAGE_SIZE_MB", 10)) * 1024 * 1024
            resp = httpx.get(src, timeout=15.0, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
            if len(data) > max_bytes:
                logger.warning("[ImageService] image too large (%d bytes): %s", len(data), src)
                return None
            ctype = (resp.headers.get("content-type", "") or "").split(";")[0].strip().lower()
            if ctype not in MIME_TO_EXT:
                ctype = self._guess_mime(src, data)
            return data, ctype, MIME_TO_EXT.get(ctype, self._ext_from_filename(src))
        except Exception as exc:
            logger.warning("[ImageService] download failed %s: %s", src, exc)
            return None

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _build_storage_key(sha: str, ext: str) -> str:
        """内容寻址 + 分片目录，避免单目录文件过多。"""
        return f"{sha[:2]}/{sha[2:4]}/{sha}{ext}"

    @staticmethod
    def _rewrite_srcs(content: str, mapping: Dict[str, str]) -> str:
        for src, url in mapping.items():
            content = content.replace(src, url)
        return content

    @staticmethod
    def _guess_mime(filename: str, data: bytes = b"") -> str:
        ext = Path(filename).suffix.lower()
        if ext in EXT_TO_MIME:
            return EXT_TO_MIME[ext]
        # magic bytes 嗅探
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        return "image/png"

    @staticmethod
    def _ext_from_filename(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        return ext if ext in EXT_TO_MIME else ".png"
