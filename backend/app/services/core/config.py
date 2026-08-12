"""RAG 系统配置中心"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ChunkingConfig:
    paragraph_size: int = 800
    paragraph_overlap: int = 200
    sentence_size: int = 200
    sentence_overlap: int = 50
    document_max_chars: int = 2000


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model_name: str = "BAAI/bge-small-zh-v1.5"
    device: str = "cpu"
    batch_size: int = 32
    dimension: int = 512
    normalize: bool = True
    api_url: str = ""
    api_key: str = ""
    api_model: str = "text-embedding-3-small"
    cache_enabled: bool = True
    cache_max_size: int = 10000


@dataclass
class RetrievalConfig:
    dense_top_k: int = 20
    sparse_top_k: int = 20
    hybrid_top_k: int = 20
    rrf_k: int = 60
    milvus_nprobe: int = 16


@dataclass
class RerankerConfig:
    enabled: bool = True
    model_name: str = "BAAI/bge-reranker-base"
    top_k: int = 5
    device: str = "cpu"
    mmr_lambda: float = 0.7


@dataclass
class ContextConfig:
    # DeepSeek v4: 1M tokens 上下文
    # 换算: 1 中文 ≈ 0.6 token, 1 英文 ≈ 0.3 token
    # 预算分配:
    #   - system prompt:  ~2,000 tokens
    #   - 用户问题+指令:  ~2,000 tokens
    #   - 检索上下文:    剩余 ~996,000 tokens
    # 安全余量 30%:     ~700,000 tokens
    max_tokens: int = 700_000
    # 不限制文档数量和单篇文档大小，按总 tokens 统一控制


@dataclass
class RAGConfig:
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    debug: bool = False


DEFAULT_CONFIG = RAGConfig()
