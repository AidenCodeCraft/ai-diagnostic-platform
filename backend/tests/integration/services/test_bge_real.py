"""BGE 本地模型真实集成测试（默认 skip，不阻塞默认全量 pytest / CI）。

覆盖缺口：huggingface.co 被墙场景下，BGE 本地模型「真实下载 + 加载 + 语义质量 +
离线可复现 + Milvus 联合检索」从未被真实验证过；默认测试 conftest 强制
``EMBEDDING_PROVIDER=hash``，只覆盖哈希兜底分支。

门槛（全部满足才真正执行）：
    RUN_REAL_BGE=1        必须显式设置（默认整模块 skip）
    模型已缓存            BAAI/bge-small-zh-v1.5 的 HF 缓存完整（否则 skip）

注意：模块被启用（RUN_REAL_BGE=1）时会自动强制 ``HF_HUB_OFFLINE=1`` /
``TRANSFORMERS_OFFLINE=1`` —— 否则 transformers 会对 repo id 发起
``find_adapter_config_file()`` 元数据探测；在 huggingface.co 不可达的环境下该
HTTP 请求会长时间挂起（实测卡住 7+ 分钟），与模型是否已缓存无关。
    RUN_REAL_BGE_OFFLINE=1  可选：额外跑「HF_HUB_OFFLINE=1 子进程加载」用例
                            （会再启动一个 python 进程，Windows 上可耗时数分钟）
    localhost:19530 可连   可选：Milvus 联合检索用例，不可连则该用例 skip

运行示例（在 backend/ 目录下；Windows PowerShell）::

    # 只跑模型本身（加载 / 语义 / 归一化 / batch 一致性），约需数分钟（torch 冷启动）
    $env:RUN_REAL_BGE='1'
    ..\\.venv\\Scripts\\python.exe -X utf8 -m pytest `
        tests/integration/services/test_bge_real.py -v

    # 追加离线加载 + Milvus 联合检索（需 Milvus 已启动）
    $env:RUN_REAL_BGE_OFFLINE='1'
    ..\\.venv\\Scripts\\python.exe -X utf8 -m pytest `
        tests/integration/services/test_bge_real.py -v

默认（不设置 RUN_REAL_BGE）时本文件只显示为 skipped，不影响全量 pytest。
"""

from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

RUN_REAL_BGE = os.getenv("RUN_REAL_BGE", "").strip().lower() in ("1", "true", "yes", "on")
RUN_REAL_BGE_OFFLINE = os.getenv("RUN_REAL_BGE_OFFLINE", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
MODEL_NAME = os.getenv("BGE_MODEL_NAME", "BAAI/bge-small-zh-v1.5")

BACKEND_DIR = Path(__file__).resolve().parents[3]  # backend/
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530") or 19530)
MILVUS_DOC_ID = 9999
MILVUS_DOC_CONTENT = "USB 设备超时无响应的排查方法：检查线缆、驱动与供电"
MILVUS_QUERY = "USB 超时"

pytestmark = pytest.mark.skipif(
    not RUN_REAL_BGE,
    reason="BGE 真实模型集成测试默认跳过；设置 RUN_REAL_BGE=1 且模型已缓存时启用",
)

if RUN_REAL_BGE:
    # 重要（实测坑）：本模块只使用「已缓存的模型」，必须强制离线加载。
    # 否则 transformers 会对 repo id 执行 find_adapter_config_file() 等元数据探测，
    # 在 huggingface.co 被墙的环境下该 HTTP 连接会长时间挂起（实测 pytest 卡住 7+ 分钟），
    # 与模型是否已经缓存无关。HF_ENDPOINT 仅作为「显式允许联网」时的兜底镜像。
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault(
        "HF_ENDPOINT", os.getenv("HF_ENDPOINT") or "https://hf-mirror.com"
    )

# 语义质量样本：每组 (查询, 语义相近句, 语义无关句)
SEMANTIC_GROUPS: List[Tuple[str, str, str]] = [
    ("USB 设备超时无响应", "USB 接口通信超时", "磁盘空间不足导致服务崩溃"),
    ("内核 panic 导致系统重启", "Kernel panic 触发系统崩溃重启", "数据库连接池耗尽导致请求失败"),
    ("网络丢包严重导致通信中断", "网卡丢包引起数据传输中断", "内存 OOM 导致服务进程被杀死"),
    ("内存 OOM 导致服务进程被杀死", "内存溢出 OutOfMemory 进程崩溃", "USB 设备超时无响应"),
]


# ----------------------------------------------------------------------
# 缓存 / 依赖探测
# ----------------------------------------------------------------------
def _hub_cache_dir() -> Path:
    env = os.environ
    if env.get("HF_HUB_CACHE"):
        return Path(env["HF_HUB_CACHE"])
    if env.get("HUGGINGFACE_HUB_CACHE"):
        return Path(env["HUGGINGFACE_HUB_CACHE"])
    if env.get("HF_HOME"):
        return Path(env["HF_HOME"]) / "hub"
    if env.get("XDG_CACHE_HOME"):
        return Path(env["XDG_CACHE_HOME"]) / "huggingface" / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _repo_cache_dir() -> Path:
    return _hub_cache_dir() / ("models--" + MODEL_NAME.replace("/", "--"))


def _find_cached_snapshot() -> Optional[Path]:
    """返回完整可用的 snapshot 目录；未缓存 / 不完整返回 None。"""
    repo_dir = _repo_cache_dir()
    if not repo_dir.is_dir():
        return None
    commit: Optional[str] = None
    ref = repo_dir / "refs" / "main"
    try:
        commit = ref.read_text(encoding="utf-8").strip() or None
    except OSError:
        commit = None

    candidates: List[Path] = []
    if commit:
        candidates.append(repo_dir / "snapshots" / commit)
    snapshots_dir = repo_dir / "snapshots"
    if snapshots_dir.is_dir():
        candidates.extend(p for p in sorted(snapshots_dir.iterdir()) if p.is_dir())

    for snapshot in candidates:
        if not (snapshot / "config.json").is_file():
            continue
        weights = [
            p
            for p in (snapshot / "model.safetensors", snapshot / "pytorch_model.bin")
            if p.is_file()
        ]
        if not weights:
            continue
        if max(p.stat().st_size for p in weights) < 50 * 1024 * 1024:
            continue  # 下载中断导致的残缺权重
        return snapshot
    return None


def _milvus_reachable() -> bool:
    try:
        with socket.create_connection((MILVUS_HOST, MILVUS_PORT), timeout=2.0):
            return True
    except OSError:
        return False


def _require_sentence_transformers() -> None:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError as exc:  # pragma: no cover - 环境缺依赖时 skip
        pytest.skip(f"sentence-transformers 未安装（见 requirements-ml.txt）: {exc}")


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def snapshot_dir() -> Path:
    snapshot = _find_cached_snapshot()
    if snapshot is None:
        pytest.skip(
            f"BGE 模型未缓存（{_repo_cache_dir()}）。先运行 "
            "backend/scripts/verify/bge_embedding_e2e.py 下载模型"
        )
    return snapshot


@pytest.fixture(scope="module")
def embedder(snapshot_dir: Path):
    """真实加载 BGEEmbedder（module 级，只加载一次）。"""
    _require_sentence_transformers()
    from app.services.core.config import EmbeddingConfig
    from app.services.knowledge.embedding import BGEEmbedder

    config = EmbeddingConfig(
        provider="local",
        model_name=MODEL_NAME,
        device="cpu",
        normalize=True,
        dimension=512,
    )
    return BGEEmbedder(config)


def _cosine(vec_a: List[float], vec_b: List[float]) -> float:
    dot = math.fsum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(math.fsum(a * a for a in vec_a))
    norm_b = math.sqrt(math.fsum(b * b for b in vec_b))
    assert norm_a and norm_b, "向量 norm 不应为 0"
    return dot / (norm_a * norm_b)


# ----------------------------------------------------------------------
# 1. 磁盘缓存证据
# ----------------------------------------------------------------------
def test_model_cache_present(snapshot_dir: Path) -> None:
    """模型真实落盘：权重 ≥50MB、config hidden_size=512、sentence-transformers 布局完整。"""
    weights = [
        p
        for p in (snapshot_dir / "model.safetensors", snapshot_dir / "pytorch_model.bin")
        if p.is_file()
    ]
    assert weights, "缺少模型权重文件"
    assert max(p.stat().st_size for p in weights) > 50 * 1024 * 1024

    cfg = json.loads((snapshot_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg.get("hidden_size") == 512, f"config hidden_size 应为 512，实际 {cfg.get('hidden_size')}"
    assert cfg.get("model_type") == "bert"
    assert (snapshot_dir / "modules.json").is_file(), "缺少 sentence-transformers modules.json"
    assert (snapshot_dir / "tokenizer.json").is_file()

    print(f"\n[BGE] 缓存: {snapshot_dir}")
    print(f"[BGE] 权重: {[(p.name, p.stat().st_size) for p in weights]}")


# ----------------------------------------------------------------------
# 2. 加载与维度
# ----------------------------------------------------------------------
def test_embedder_loads_dimension_512(embedder) -> None:
    """真实加载成功，dimension=512，health_check 通过，嵌入非空。"""
    assert embedder.health_check() is True
    assert embedder.dimension == 512
    vec = embedder.embed("USB 设备超时无响应")
    assert len(vec) == 512
    assert all(isinstance(v, float) for v in vec)
    assert any(abs(v) > 1e-6 for v in vec), "嵌入向量不应全为 0"


# ----------------------------------------------------------------------
# 3. 语义质量
# ----------------------------------------------------------------------
def test_semantic_similarity_ordering(embedder) -> None:
    """相近句余弦相似度必须显著高于无关句（4 组中文故障语义样本）。"""
    for query_text, similar, dissimilar in SEMANTIC_GROUPS:
        vec_query = embedder.embed(query_text)
        vec_close = embedder.embed(similar)
        vec_far = embedder.embed(dissimilar)
        sim_close = _cosine(vec_query, vec_close)
        sim_far = _cosine(vec_query, vec_far)
        assert sim_close > sim_far, (
            f"语义排序错误: {query_text!r} vs {similar!r}={sim_close:.4f} "
            f"不应低于 vs {dissimilar!r}={sim_far:.4f}"
        )
        print(
            f"\n[BGE] {query_text!r}: 相近={sim_close:.4f} 无关={sim_far:.4f} "
            f"delta={sim_close - sim_far:+.4f}"
        )

    # 「USB 超时」这组的区分度额外要求显著（>0.10）
    usb_query, usb_close, usb_far = SEMANTIC_GROUPS[0]
    usb_delta = _cosine(
        embedder.embed(usb_query), embedder.embed(usb_close)
    ) - _cosine(embedder.embed(usb_query), embedder.embed(usb_far))
    assert usb_delta > 0.10, f"USB 样本区分度不足: delta={usb_delta:.4f}"


def test_vectors_are_normalized(embedder) -> None:
    """normalize=True 时向量 L2 norm ≈ 1.0。"""
    for query, _similar, _dissimilar in SEMANTIC_GROUPS:
        norm = math.sqrt(math.fsum(v * v for v in embedder.embed(query)))
        assert abs(norm - 1.0) < 1e-3, f"{query!r} norm={norm}"

    # 相近 / 无关句的余弦应在合理范围（BGE-zh 相似句通常 0.6+）
    query, similar, dissimilar = SEMANTIC_GROUPS[0]
    assert _cosine(embedder.embed(query), embedder.embed(similar)) > 0.6


def test_batch_matches_single(embedder) -> None:
    """batch embed 与逐条 embed 结果在 float 误差内一致。"""
    texts = [group[0] for group in SEMANTIC_GROUPS]
    build = getattr(embedder, "_cache", None)
    if isinstance(build, dict):
        build.clear()
    single = [embedder.embed(text) for text in texts]
    if isinstance(build, dict):
        build.clear()
    batch = embedder.embed_batch(texts)
    assert len(batch) == len(single)
    max_diff = max(
        abs(a - b) for single_vec, batch_vec in zip(single, batch) for a, b in zip(single_vec, batch_vec)
    )
    assert max_diff < 1e-5, f"batch 与单条最大差异 {max_diff}"


# ----------------------------------------------------------------------
# 4. 离线加载（子进程，可选）
# ----------------------------------------------------------------------
_OFFLINE_CHILD_CODE = r"""
import json, os, sys
sys.path.insert(0, os.environ["BGE_TEST_BACKEND_DIR"])
from app.services.core.config import EmbeddingConfig
from app.services.knowledge.embedding import BGEEmbedder
emb = BGEEmbedder(
    EmbeddingConfig(provider="local", model_name=os.environ["BGE_TEST_MODEL"], device="cpu", normalize=True)
)
vec = emb.embed("USB 设备超时无响应")
norm = sum(x * x for x in vec) ** 0.5
print("OFFLINE_CHILD_RESULT: " + json.dumps({"dimension": emb.dimension, "norm": norm}))
"""


@pytest.mark.skipif(
    not RUN_REAL_BGE_OFFLINE,
    reason="离线子进程加载用例默认跳过；设置 RUN_REAL_BGE_OFFLINE=1 启用",
)
def test_offline_load_by_repo_id(snapshot_dir: Path) -> None:
    """HF_HUB_OFFLINE=1 + 无效 HF_ENDPOINT 的新进程仍能按 repo id 加载（离线可部署）。"""
    env = dict(os.environ)
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    # 无效端点：任何网络尝试都会失败，成功即证明完全走本地缓存
    env["HF_ENDPOINT"] = "https://offline.invalid.example"
    env["BGE_TEST_BACKEND_DIR"] = str(BACKEND_DIR)
    env["BGE_TEST_MODEL"] = MODEL_NAME
    env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", _OFFLINE_CHILD_CODE],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )
    assert completed.returncode == 0, f"离线加载失败:\n{completed.stderr[-3000:]}"
    payload = None
    for line in reversed((completed.stdout or "").splitlines()):
        if line.startswith("OFFLINE_CHILD_RESULT: "):
            payload = json.loads(line[len("OFFLINE_CHILD_RESULT: "):])
            break
    assert payload is not None, f"子进程未输出结果:\n{completed.stdout[-2000:]}"
    assert payload["dimension"] == 512
    assert abs(payload["norm"] - 1.0) < 1e-3, f"norm={payload['norm']}"


# ----------------------------------------------------------------------
# 5. Milvus 联合检索（可选）
# ----------------------------------------------------------------------
def test_milvus_joint_index_search(monkeypatch) -> None:
    """BGE 向量真实写入 Milvus：index(doc 9999) → search 命中 → 清理删除。"""
    if not _milvus_reachable():
        pytest.skip(f"Milvus {MILVUS_HOST}:{MILVUS_PORT} 不可连接（未启动则跳过）")
    _require_sentence_transformers()

    from app.core.config import settings
    from app.services.knowledge import embedding as embedding_module

    monkeypatch.setattr(settings, "MILVUS_ENABLED", True)
    monkeypatch.setattr(settings, "MILVUS_HOST", MILVUS_HOST)
    monkeypatch.setattr(settings, "MILVUS_PORT", MILVUS_PORT)
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "local")
    monkeypatch.setattr(settings, "EMBEDDING_DIM", 512)
    monkeypatch.setattr(settings, "EMBEDDING_LOAD_TIMEOUT", 300.0)
    monkeypatch.setattr(settings, "EMBEDDING_HASH_FALLBACK", False)

    # 重置 embedder 单例，确保 VectorService 使用 local(BGE) 而非其它测试留下的 hash
    monkeypatch.setattr(embedding_module, "_global_embedder", None)

    from app.services.knowledge.vector_service import VectorService

    service = VectorService()
    assert service.available is True, "VectorService 应可用（Milvus 连接 + BGE 加载）"
    assert service.dimension == 512

    try:
        chunks = service.index_document(MILVUS_DOC_ID, content=MILVUS_DOC_CONTENT)
        assert chunks > 0, "index_document 应写入至少 1 个 chunk"

        hits = service.search(MILVUS_QUERY, top_k=3)
        assert hits, "Milvus 语义检索应返回命中"
        hit_ids = [hit.get("id") for hit in hits]
        assert MILVUS_DOC_ID in hit_ids, f"应命中 doc {MILVUS_DOC_ID}，实际 {hit_ids}"
        print(f"\n[BGE+Milvus] {MILVUS_QUERY!r} 命中: {hits}")
    finally:
        cleaned = service.delete_document(MILVUS_DOC_ID)
        assert cleaned, "清理 delete_document 应成功"
        remain = service._collection.query(  # noqa: SLF001 - 验证清理结果
            f"doc_id == {MILVUS_DOC_ID}", output_fields=["id"]
        )
        assert remain == [], f"清理后仍能查到 doc {MILVUS_DOC_ID}: {remain}"
