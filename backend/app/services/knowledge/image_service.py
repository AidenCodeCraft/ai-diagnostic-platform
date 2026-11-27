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
        section_range: Optional[Tuple[int, int]] = None,
        content: Optional[str] = None,
    ) -> List[KnowledgeImage]:
        """为命中文档挑选关联图片 —— 图片必须属于「命中章节」这个知识点。

        策略（按优先级）：
          1. 命中章节的行号区间可用时：只保留位于该区间内的图片。
             图片在文档中的位置由其前文 context_text 定位；
             区间外的图片直接排除——即使文本有零星重合（如只撞上 "gps" 这种通用词），
             因为它属于另一个知识点的配图。
          2. 区间不可用 → 图片锚点与命中章节匹配 → 返回该章节图片。
          3. 再退化 → 按「图片文本与查询主题的重合度」筛选。
          4. 没有任何信号时返回空列表 —— 宁可不展示，也不展示图不对文的图片。
        """
        images = self.list_images(doc_id)
        if not images:
            return []

        penalties = self._feedback_penalties(images)
        candidates = images

        # 1) 章节区间过滤：图片属于哪个知识点，由它在文档中的位置决定
        start, end = section_range or (0, 0)
        ranged = (start, end) if start > 0 and end >= start else None
        # 检索层返回的章节经常没有行号（_section 里 start_line/end_line 为 None），
        # 而锚点「关键字解释」这类小节名在同一篇文档里会重复出现 N 次。
        # 只按锚点匹配就会把同名小节里别的知识点的配图挂上来——所以有正文时先把区间算出来。
        anchor_ambiguous = False
        if content and anchor:
            located = self._locate_section_range(content, anchor, query)
            if located:
                ranged = located
            else:
                # 有正文却定位不出这一节：多半是「关键字解释」这类同名小节重复出现。
                # 此时锚点匹配毫无区分度（会把别的知识点的配图挂上来），只能靠主题重合度。
                anchor_ambiguous = True
        if content and ranged:
            inside: List[KnowledgeImage] = []
            for img in images:
                line = self._image_line(content, img)
                if line is not None and ranged[0] <= line <= ranged[1]:
                    inside.append(img)
                # 区间外/定位不了 → 不属于这一节，排除
            return self._rank_with_penalty(inside, penalties, top_k)

        # 2) 章节锚点匹配（仅在拿不到正文、无法按行号定位时使用）
        a = (anchor or "").strip()
        if a and candidates and not anchor_ambiguous:
            matched = [img for img in candidates if self._anchor_matches(img.anchor, a)]
            if matched:
                return self._rank_with_penalty(matched, penalties, top_k)

        # 3) 查询主题重合度
        if query.strip() and candidates:
            scored = [
                (self._text_relevance(img, query) - 0.3 * penalties.get(img.id, 0), img)
                for img in candidates
            ]
            scored = [x for x in scored if x[0] > 0]
            if scored:
                scored.sort(key=lambda x: (-x[0], x[1].position or 0))
                return [img for _, img in scored[:top_k]]

        return []

    @staticmethod
    def _image_line(content: str, img: KnowledgeImage) -> Optional[int]:
        """图片在文档中的行号。

        context_text 是以图片为中心的 ±120 字窗口（前文 + 图片 + 后文），
        所以必须先切出「图片之前」的那段前文再定位——直接用整段/尾部会定位到图片后面。
        无法唯一定位（前文缺失/在文档中出现多次）时返回 None，调用方按"未知"处理。
        """
        if not content:
            return None
        ctx = (img.context_text or "").strip()
        if not ctx:
            return None
        marker = re.search(r"!\[[^\]]*\]\([^)]*\)", ctx)
        pre = ctx[: marker.start()] if marker else ctx
        pre = pre.strip("\n")
        if not pre.strip():
            return None
        for window in (120, 60, 30, 12):
            if len(pre) < window:
                continue
            tail = pre[-window:]
            first = content.find(tail)
            if first < 0:
                continue
            if content.find(tail, first + 1) >= 0:
                return None  # 多处出现，无法唯一定位
            return content.count("\n", 0, first + len(tail)) + 1
        return None


    # ── 章节定位（锚点 → 行号区间）────────────────────────────
    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    _NUMBERING_RE = re.compile(r"^[0-9一二三四五六七八九十]+[.、．)）]\s*")

    @classmethod
    def _norm_heading(cls, text: str) -> str:
        s = cls._NUMBERING_RE.sub("", (text or "").strip())
        return re.sub(r"\s+", "", s)

    @classmethod
    def _heading_matches(cls, heading: str, segment: str) -> bool:
        a, b = cls._norm_heading(heading), cls._norm_heading(segment)
        if not a or not b:
            return False
        return a == b or a.endswith(b) or b.endswith(a)

    def _headings(self, lines: list[str]) -> list[tuple[int, int, str]]:
        """正文里所有标题：(0-based 行下标, 级别, 标题文字)。"""
        out = []
        for i, line in enumerate(lines):
            m = self._HEADING_RE.match(line)
            if m:
                out.append((i, len(m.group(1)), m.group(2)))
        return out

    def _section_bounds(self, heads, h_i: int, level: int, window_end: int) -> int:
        """从标题行往后找同级或更高级标题，返回该小节最后一行（0-based）。"""
        for h2, level2, _text in heads:
            if h2 > h_i and level2 <= level and h2 <= window_end:
                return h2 - 1
        return window_end

    def _locate_section_range(
        self, content: str, anchor: str, query: str = "",
    ) -> Optional[Tuple[int, int]]:
        """把章节锚点定位成 (start_line, end_line)（1-based，含行）。

        锚点可能是层级标题（`4. TMP更新XML > 关键字解释`）：逐级收窄窗口，
        子标题只在父标题范围内找，这样同名小节不会互相串台。
        """
        if not content or not anchor:
            return None
        lines = content.split(chr(10))
        heads = self._headings(lines)
        if not heads:
            return None

        window_start, window_end = 0, len(lines) - 1
        found: Optional[Tuple[int, int]] = None
        for segment in [s.strip() for s in re.split(r"[>›/]", anchor) if s.strip()]:
            cands = [
                h for h in heads
                if window_start <= h[0] <= window_end and self._heading_matches(h[2], segment)
            ]
            if not cands:
                return found
            if len(cands) > 1:
                best = self._pick_heading(cands, lines, query)
                if best is None:
                    # 同名小节且没有足够线索区分 → 不猜，宁可不给区间
                    return found
                cands = [best]
            h_i, level, _text = cands[0]
            end = self._section_bounds(heads, h_i, level, window_end)
            found = (h_i + 1, end + 1)  # 转 1-based
            window_start, window_end = h_i, end
        return found

    @classmethod
    def _pick_heading(cls, cands, lines: list[str], query: str):
        """多个同名小节时，用查询主题词在各自正文里的重合度挑唯一最优；挑不出来返回 None。"""
        runs = [r for r in re.findall(r"[一-鿿]{4,}|[a-z0-9_]{4,}", (query or "").lower())]
        if not runs:
            return None
        heads = [(i, len(m.group(1)), m.group(2)) for i, l in enumerate(lines)
                 if (m := cls._HEADING_RE.match(l))]
        scored = []
        for h_i, level, _text in cands:
            end = len(lines)
            for h2, level2, _t2 in heads:
                if h2 > h_i and level2 <= level:
                    end = h2
                    break
            body = chr(10).join(lines[h_i + 1:end]).lower()
            scored.append((sum(1 for r in runs if r in body), h_i))
        scored.sort(reverse=True)
        if not scored or scored[0][0] == 0:
            return None
        if len(scored) > 1 and scored[1][0] == scored[0][0]:
            return None
        target = scored[0][1]
        return next((h for h in cands if h[0] == target), None)

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

    # 查询主题重合度门槛：长词组至少连续命中 6 字，短词组（≤6 字）须整段命中
    _MIN_TOPIC_OVERLAP = 6

    @classmethod
    def _text_relevance(cls, img: KnowledgeImage, query: str) -> float:
        """图片文本与查询主题的重合度（0~1）；判定不相关时返回 0。

        旧实现把整段中文查询当成一个词去匹配，几乎永远匹配不上，
        于是每次都落到"按位置兜底"，把无关图片也带出来。

        现在：把查询拆成中文/英文词组，逐个计算与图片文本的最长公共子串，
        词组较短（≤6 字）必须整段命中，较长的至少连续命中 6 字才算相关。
        例：查"设备端日志搜索版本号什么关键字"，图片上下文只有"日志搜索"（4 字）
            重合 → 判定不相关；查"线路运行方向相反"整段命中 → 相关。
        """
        # 章节名与标题行不能算作「图片内容」：否则同名小节（关键字解释 ×N）
        # 会让每张图都命中查询里的章节名，等价于没有区分度。
        ctx = re.sub(r"(?m)^\s{0,3}#{1,6}.*$", " ", img.context_text or "")
        anchor_text = (img.anchor or "").strip()
        if anchor_text:
            ctx = ctx.replace(anchor_text, " ")
        text = " ".join(
            x for x in [img.caption or "", ctx] if x
        ).lower()
        q = (query or "").lower().strip()
        if not text or not q:
            return 0.0

        best = 0.0
        for run in re.findall(r"[一-鿿]{2,}|[a-z0-9_]{3,}", q):
            if run[0].isascii():
                # 短英文缩写（gps / usb / tmp 这类）区分度太低，
                # 单独命中不足以判定"图片与问题相关"；含数字的型号（l10、fc09、9206）除外
                if not (len(run) >= 4 or (len(run) >= 3 and any(c.isdigit() for c in run))):
                    continue
            elif len(run) < 4:
                # 2-3 字中文（上报 / 日志 / 关键字…）在语料里到处都是，
                # 不足以单独判定图片相关；真正对题的表述通常 ≥4 字
                continue
            overlap = cls._min_common_substring(run, text)
            if overlap:
                best = max(best, overlap / len(run))
        return best

    @classmethod
    def _min_common_substring(cls, a: str, b: str) -> int:
        """a、b 之间长度 ≥ min(6, len(a)) 的最长公共子串长度；不足则返回 0。"""
        need = min(cls._MIN_TOPIC_OVERLAP, len(a))
        upper = min(len(a), len(b))
        for size in range(upper, need - 1, -1):
            for i in range(len(a) - size + 1):
                if a[i:i + size] in b:
                    return size
        return 0

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
