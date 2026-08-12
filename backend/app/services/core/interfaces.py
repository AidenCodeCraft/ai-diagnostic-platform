"""RAG 系统核心接口抽象层。

参照 DeepSeek RAG 架构的模块化设计，定义所有核心组件的抽象接口。
遵循依赖倒置原则 (DIP)：高层模块不依赖低层模块，都依赖抽象。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Tuple


# =========================================================================
# 数据传输对象 (DTOs)
# =========================================================================


@dataclass
class Chunk:
    """文档块 — 统一的检索单元"""
    id: str = ""                          # 唯一标识
    text: str = ""                        # 块文本
    doc_id: int = 0                       # 所属文档 ID
    doc_title: str = ""                   # 文档标题
    section_title: str = ""               # 所属章节标题
    granularity: str = "paragraph"        # document | paragraph | sentence
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """单条检索结果"""
    chunk: Chunk = field(default_factory=Chunk)
    score: float = 0.0
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rerank_score: float = 0.0
    rank_position: int = 0


@dataclass
class RetrievalOutput:
    """完整检索输出"""
    query: str
    results: List[SearchResult] = field(default_factory=list)
    total_candidates: int = 0
    total_retrieved: int = 0
    latency_ms: float = 0.0
    pipeline_stages: Dict[str, float] = field(default_factory=dict)


# =========================================================================
# 抽象接口
# =========================================================================


class IEmbedder(ABC):
    """文本嵌入器接口"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        ...

    def health_check(self) -> bool:
        return True


class IRetriever(ABC):
    """检索器接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def retrieve(
        self, query: str, top_k: int = 20, **kwargs: Any,
    ) -> List[SearchResult]:
        ...

    def health_check(self) -> bool:
        return True


class IReranker(ABC):
    """重排序器接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def rerank(
        self, query: str, documents: List[str], top_k: int = 5,
    ) -> List[Tuple[int, float]]:
        ...

    def health_check(self) -> bool:
        return True


class IGenerator(ABC):
    """LLM 生成器接口"""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        ...

    @abstractmethod
    def generate_stream(
        self, system_prompt: str, user_prompt: str,
    ) -> Generator[str, None, None]:
        ...
