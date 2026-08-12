"""Embedding 层 — BGE 本地语义向量 + API 云端备选。

硬依赖: sentence-transformers (BGE 模型)
备选: APIEmbedder (OpenAI 兼容接口，需配置 api_url + api_key)

启动时自动检测依赖，缺失则报错退出（不再使用 pseudo_embed 兜底）。
"""

from __future__ import annotations
import hashlib
import logging
from typing import Dict, List, Optional, Tuple

from app.services.core.interfaces import IEmbedder
from app.services.core.config import EmbeddingConfig

logger = logging.getLogger(__name__)

# 启动依赖检查
_sentence_transformers_available = False
try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    _sentence_transformers_available = True
except ImportError:
    pass


class BGEEmbedder(IEmbedder):
    """本地 BGE 语义嵌入器。

    使用 sentence-transformers 加载 BGE 模型。
    模型选择: BAAI/bge-small-zh-v1.5 (512维, ~20ms/条, CPU可运行)
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        if not _sentence_transformers_available:
            raise RuntimeError(
                "BGE Embedding 需要 sentence-transformers，请执行: pip install sentence-transformers"
            )
        self.config = config or EmbeddingConfig()
        self._model = None
        self._cache: Dict[str, List[float]] = {}
        self._init_model()

    @property
    def dimension(self) -> int:
        if self._model is not None:
            try:
                return self._model.get_sentence_embedding_dimension()
            except Exception:
                pass
        return self.config.dimension

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.dimension
        key = self._cache_key(text)
        if key in self._cache:
            return self._cache[key]
        vec = self.embed_batch([text])[0]
        if self.config.cache_enabled and len(self._cache) < self.config.cache_max_size:
            self._cache[key] = vec
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        valid = [t.strip() for t in texts if t.strip()]
        if not valid:
            return [[0.0] * self.dimension for _ in texts]

        results: List[Optional[List[float]]] = [None] * len(valid)
        uncached_idx, uncached_txt = [], []
        for i, t in enumerate(valid):
            key = self._cache_key(t)
            if key in self._cache:
                results[i] = self._cache[key]
            else:
                uncached_idx.append(i)
                uncached_txt.append(t)

        if uncached_txt:
            vecs = self._encode(uncached_txt)
            for idx, vec in zip(uncached_idx, vecs):
                results[idx] = vec
                if self.config.cache_enabled and len(self._cache) < self.config.cache_max_size:
                    self._cache[self._cache_key(valid[idx])] = vec

        return [r if r else [0.0] * self.dimension for r in results]

    def health_check(self) -> bool:
        return self._model is not None

    def _init_model(self) -> None:
        from sentence_transformers import SentenceTransformer
        logger.info("[Embedding] Loading BGE model: %s", self.config.model_name)
        self._model = SentenceTransformer(self.config.model_name, device=self.config.device)
        logger.info("[Embedding] BGE model loaded, dim=%d", self.dimension)

    def _encode(self, texts: List[str]) -> List[List[float]]:
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=self.config.normalize,
            show_progress_bar=False,
            batch_size=min(self.config.batch_size, len(texts)),
        )
        return [emb.tolist() for emb in embeddings]

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()


class APIEmbedder(IEmbedder):
    """云端 Embedding API 嵌入器 — OpenAI 兼容接口。

    需要配置 EmbeddingConfig 中的 api_url 和 api_key。
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self._cache: Dict[str, List[float]] = {}

    @property
    def dimension(self) -> int:
        return self.config.dimension

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.dimension
        key = self._cache_key(text)
        if key in self._cache:
            return self._cache[key]
        vec = self.embed_batch([text])[0]
        if self.config.cache_enabled and len(self._cache) < self.config.cache_max_size:
            self._cache[key] = vec
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        import requests
        valid = [t.strip() for t in texts if t.strip()]
        if not valid:
            return [[0.0] * self.dimension for _ in texts]

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.config.api_model, "input": valid}

        resp = requests.post(self.config.api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    def health_check(self) -> bool:
        return bool(self.config.api_url and self.config.api_key)

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()


class EmbeddingService:
    """Embedding 统一入口 — 替换旧的 EmbeddingService 类。

    策略: BGE 本地模型优先，API 云端备选。
    BGE 不可用时自动切换 API，API 也不可用则报错。

    保留 embed_with_chunks 方法兼容旧调用方。
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self._bge: Optional[BGEEmbedder] = None
        self._api: Optional[APIEmbedder] = None
        self._active: Optional[IEmbedder] = None
        self._init()

    @property
    def dimension(self) -> int:
        return self._get_active().dimension

    @property
    def provider_name(self) -> str:
        return type(self._get_active()).__name__

    def embed(self, text: str) -> List[float]:
        return self._get_active().embed(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self._get_active().embed_batch(texts)

    def embed_with_chunks(
        self, text: str, chunk_size: int = 500, overlap: int = 50,
    ) -> List[Tuple[str, List[float]]]:
        chunks = self._chunk_text(text, chunk_size, overlap)
        if not chunks:
            return []
        embeddings = self.embed_batch(chunks)
        return list(zip(chunks, embeddings))

    def health_check(self) -> bool:
        return self._active is not None and self._active.health_check()

    def clear_cache(self) -> None:
        for e in [self._bge, self._api]:
            if e and hasattr(e, '_cache'):
                getattr(e, '_cache').clear()

    def _init(self) -> None:
        # 优先 BGE
        if _sentence_transformers_available:
            try:
                self._bge = BGEEmbedder(self.config)
                if self._bge.health_check():
                    self._active = self._bge
                    return
            except Exception as e:
                logger.warning("[Embedding] BGE init failed: %s", e)

        # 备选 API
        self._api = APIEmbedder(self.config)
        if self._api.health_check():
            self._active = self._api
            logger.info("[Embedding] Using API embedder")
            return

        raise RuntimeError(
            "Embedding 服务不可用。请安装 sentence-transformers "
            "或配置 EMBEDDING_API_URL 和 EMBEDDING_API_KEY。"
        )

    def _get_active(self) -> IEmbedder:
        if self._active is None:
            raise RuntimeError("Embedding 服务未初始化")
        if not self._active.health_check():
            self._init()
        return self._active

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        if len(text) <= chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                for sep in ['\n\n', '\n', '。', '. ', '! ', '? ']:
                    idx = text.rfind(sep, start, end)
                    if idx > start + chunk_size // 2:
                        end = idx + len(sep)
                        break
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - overlap
        return chunks


# 全局单例
_global_embedder: Optional[EmbeddingService] = None


def get_embedder(config: Optional[EmbeddingConfig] = None) -> EmbeddingService:
    global _global_embedder
    if _global_embedder is None:
        _global_embedder = EmbeddingService(config)
    return _global_embedder
