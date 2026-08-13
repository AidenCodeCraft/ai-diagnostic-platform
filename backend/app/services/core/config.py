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

    # === LLM 辅助重排序（第二阶段新增） ===
    # 当 Cross-Encoder 最高分 < 此阈值时，触发 LLM 辅助重排序
    llm_fallback_enabled: bool = True
    llm_fallback_threshold: float = 0.3
    # LLM Reranker 超时（秒），超时后静默回退
    llm_fallback_timeout: float = 3.0


@dataclass
class ContextConfig:
    """上下文窗口配置 — 模型感知的动态 token 预算。

    设计原则:
      - 不再硬编码单一 max_tokens 值
      - 根据实际使用的模型动态计算预算
      - 保留 max_tokens 作为手动覆盖项（向后兼容）

    预算分配:
      - system prompt:  约 2,000 tokens
      - 用户指令:       约 2,000 tokens
      - 检索上下文:     剩余部分（按 ratio 计算）
    """

    # === 动态预算（推荐） ===

    # 对话上下文预算比例（占模型上下文窗口的比例）
    chat_budget_ratio: float = 0.6
    # 对话上下文最小预算（防止小窗口模型过于受限）
    chat_min_budget: int = 4_000

    # RAG 检索上下文预算比例（占模型上下文窗口的比例）
    rag_budget_ratio: float = 0.7
    # RAG 固定开销预留（system prompt + 用户指令）
    rag_overhead: int = 4_000

    # === 静态回退（向后兼容） ===

    # 当无法获取模型上下文窗口时，使用此固定值
    # 700K = DeepSeek v4 1M 的 70% 安全余量
    max_tokens: int = 700_000

    # 不限制文档数量和单篇文档大小，按总 tokens 统一控制

    # === 便捷方法 ===

    def get_chat_budget(self, model: str) -> int:
        """根据模型获取对话上下文预算。"""
        try:
            from app.services.core.token_counter import get_token_counter
            return get_token_counter().get_chat_budget(
                model,
                ratio=self.chat_budget_ratio,
                min_budget=self.chat_min_budget,
            )
        except Exception:
            return self.max_tokens

    def get_rag_budget(self, model: str) -> int:
        """根据模型获取 RAG 检索上下文预算。"""
        try:
            from app.services.core.token_counter import get_token_counter
            return get_token_counter().get_rag_budget(
                model,
                ratio=self.rag_budget_ratio,
                overhead=self.rag_overhead,
            )
        except Exception:
            return self.max_tokens


@dataclass
class RAGConfig:
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    debug: bool = False


DEFAULT_CONFIG = RAGConfig()
