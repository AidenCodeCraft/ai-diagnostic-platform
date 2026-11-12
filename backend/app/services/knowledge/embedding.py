"""Embedding 层 — BGE 本地语义向量 + API 云端备选。

硬依赖: sentence-transformers (BGE 模型)
备选: APIEmbedder (OpenAI 兼容接口，需配置 api_url + api_key)

启动时自动检测依赖，缺失则报错退出（不再使用 pseudo_embed 兜底）。
"""

from __future__ import annotations
import hashlib
import importlib.util
import logging
import math
import re
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.core.interfaces import IEmbedder
from app.services.core.config import EmbeddingConfig

logger = logging.getLogger(__name__)

# Detect the optional sentence-transformers dependency without importing it.
# The actual import is deliberately deferred to BGEEmbedder._init_model();
# otherwise every knowledge search would pay the torch import cost even when
# Milvus is disabled and we only need keyword search.
_sentence_transformers_available = importlib.util.find_spec("sentence_transformers") is not None


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


class HashingEmbedder(IEmbedder):
    """确定性哈希嵌入 — 无外部依赖的兜底方案。

    注意：这是「词形哈希」而非语义嵌入，仅用于本地开发/测试，
    让向量检索链路（Milvus）可以跑通；生产应使用 BGE 或 API Embedding。
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()
        self._dim = max(8, int(self.config.dimension or 512))

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def health_check(self) -> bool:
        return True

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self._dim
        for token in self._tokenize(text):
            digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            index = digest % self._dim
            sign = 1.0 if (digest >> 8) % 2 == 0 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        lowered = (text or "").lower()
        en = re.findall(r"[a-z0-9_]{2,}", lowered)
        cn_chars = re.findall(r"[\u4e00-\u9fff]", lowered)
        bigrams = ["".join(pair) for pair in zip(cn_chars, cn_chars[1:])]
        return en + cn_chars + bigrams


class EmbeddingService:
    """Embedding 统一入口 — 替换旧的 EmbeddingService 类。

    策略: BGE 本地模型优先，API 云端备选。
    BGE 不可用时自动切换 API，API 也不可用则报错。

    保留 embed_with_chunks 方法兼容旧调用方。
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or self._settings_config()
        self._bge: Optional[BGEEmbedder] = None
        self._api: Optional[APIEmbedder] = None
        self._hash: Optional[HashingEmbedder] = None
        self._active: Optional[IEmbedder] = None
        self._init()

    @staticmethod
    def _settings_config() -> EmbeddingConfig:
        """从 Settings 构建 EmbeddingConfig（env 优先于默认值）。"""
        cfg = EmbeddingConfig()
        try:
            cfg.provider = str(getattr(settings, "EMBEDDING_PROVIDER", "auto") or "auto").lower()
            cfg.dimension = int(getattr(settings, "EMBEDDING_DIM", cfg.dimension) or cfg.dimension)
            cfg.batch_size = int(getattr(settings, "EMBEDDING_BATCH_SIZE", cfg.batch_size) or cfg.batch_size)
            cfg.api_url = str(getattr(settings, "EMBEDDING_API_URL", "") or "")
            cfg.api_key = str(getattr(settings, "EMBEDDING_API_KEY", "") or "")
            cfg.api_model = str(getattr(settings, "EMBEDDING_API_MODEL", cfg.api_model) or cfg.api_model)
        except Exception:  # noqa: BLE001 - settings 缺失时回退默认配置
            pass
        return cfg

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
        provider = (self.config.provider or "auto").lower()
        allow_hash = bool(getattr(settings, "EMBEDDING_HASH_FALLBACK", True))

        if provider == "hash":
            self._activate_hash("EMBEDDING_PROVIDER=hash")
            return

        if provider in ("local", "bge"):
            if self._try_bge():
                return
            if allow_hash:
                self._activate_hash("本地 BGE 不可用")
                return
            raise RuntimeError(
                "BGE Embedding 需要 sentence-transformers，请执行: pip install sentence-transformers"
            )

        if provider == "api":
            if self._try_api():
                return
            if allow_hash:
                self._activate_hash("API Embedding 未配置")
                return
            raise RuntimeError(
                "Embedding 服务不可用。请配置 EMBEDDING_API_URL 和 EMBEDDING_API_KEY"
            )

        # auto: BGE → API → hash
        if self._try_bge():
            return
        if self._try_api():
            return
        if allow_hash:
            self._activate_hash("未检测到 BGE/API Embedding")
            return
        raise RuntimeError(
            "Embedding 服务不可用。请安装 sentence-transformers "
            "或配置 EMBEDDING_API_URL 和 EMBEDDING_API_KEY。"
        )

    def _try_bge(self) -> bool:
        if not _sentence_transformers_available:
            return False

        # BGE 首次加载可能下载模型权重；加超时避免离线环境无限阻塞
        import threading

        timeout = float(getattr(settings, "EMBEDDING_LOAD_TIMEOUT", 30.0) or 30.0)
        result: Dict[str, object] = {}

        def _load() -> None:
            try:
                result["embedder"] = BGEEmbedder(self.config)
            except Exception as exc:  # noqa: BLE001 - 记录并回退
                result["error"] = exc

        thread = threading.Thread(target=_load, daemon=True)
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            logger.warning(
                "[Embedding] BGE model load exceeded %.1fs; falling back", timeout,
            )
            return False
        if "embedder" in result:
            self._bge = result["embedder"]  # type: ignore[assignment]
            if self._bge is not None and self._bge.health_check():
                self._active = self._bge
                logger.info("[Embedding] Using local BGE embedder (dim=%d)", self._bge.dimension)
                return True
        if "error" in result:
            logger.warning("[Embedding] BGE init failed: %s", result["error"])
        return False

    def _try_api(self) -> bool:
        self._api = APIEmbedder(self.config)
        if self._api.health_check():
            self._active = self._api
            logger.info("[Embedding] Using API embedder (model=%s)", self.config.api_model)
            return True
        return False

    def _activate_hash(self, reason: str) -> None:
        self._hash = HashingEmbedder(self.config)
        self._active = self._hash
        logger.warning(
            "[Embedding] %s，使用哈希嵌入兜底（非语义向量，仅用于开发/测试）", reason,
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
