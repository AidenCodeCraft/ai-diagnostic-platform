#!/usr/bin/env python
"""Milvus 真实向量链路端到端验证脚本（可重复运行）。

覆盖链路：
1. pymilvus 2.5.4 → Milvus server 真实 gRPC 连接（打印客户端/服务端版本、已有 collection）。
2. 临时 collection 全链路（dim=512，IVF_FLAT/IP，与 VectorService 结构一致）：
   create_index → insert（HashingEmbedder 真实 512 维向量）→ flush → search 命中
   → delete 表达式 → query 确认删除 → drop（即测即清，可重复运行）。
3. 业务 collection `knowledge_docs` 状态（是否已由后端创建、实体数、向量维度）。
4. 后端 HTTP API 端到端（服务可达时执行）：
   POST /api/v1/vector/health   → milvus_available=true、embedding_provider
   POST /api/v1/vector/embed    → dimension=512
   POST /api/v1/vector/index    → chunks_indexed>0（doc_id=987654，测后删除）
   POST /api/v1/vector/search   → use_hybrid=false 时 strategy=vector_only 且命中
   POST /api/v1/vector/search   → use_hybrid=true 的 strategy（hybrid 或 keyword 兜底，仅记录）
   最后用 pymilvus 确认 knowledge_docs 实体数 >0，并清理测试向量。

用法（任选其一）：
    # 仓库根目录
    .venv\\Scripts\\python.exe backend\\scripts\\verify\\milvus_e2e.py
    # backend 目录
    python scripts\\verify\\milvus_e2e.py
    # 只跑 pymilvus 直连部分（后端未就绪时）
    python scripts\\verify\\milvus_e2e.py --skip-api

环境变量：
    MILVUS_HOST       默认 localhost
    MILVUS_PORT       默认 19530
    MILVUS_DIM        默认 512（临时 collection 与 embedding 维度）
    API_BASE_URL      默认 http://localhost:8000
    E2E_TIMEOUT       单请求超时秒数，默认 60
    EMBEDDING_PROVIDER 默认 hash（HashingEmbedder，镜像内无 torch 时的真实生效实现）

退出码：
    0 = 已执行检查全部通过（API 不可达时该段按 SKIP 处理）
    1 = 存在 FAIL 项
    2 = 前置条件不满足（pymilvus 不可导入 / Milvus 不可连接）
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Windows 管道/重定向输出时 Python 默认用本地代码页（GBK），统一为 UTF-8 避免乱码
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None and "utf" not in (_stream.encoding or "").lower():
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 老版本/特殊流忽略
        pass

# ── 必须在导入 app.* 之前设定：镜像内无 torch/sentence-transformers，
#    强制 HashingEmbedder（dim 由 EMBEDDING_DIM 决定），与生产容器实际行为一致 ──
os.environ.setdefault("EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("EMBEDDING_HASH_FALLBACK", "true")
os.environ.setdefault("EMBEDDING_DIM", os.environ.get("MILVUS_DIM", "512"))

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = str(os.getenv("MILVUS_PORT", "19530"))
DIM = int(os.getenv("MILVUS_DIM", "512") or 512)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = float(os.getenv("E2E_TIMEOUT", "60"))

TMP_COLLECTION = "milvus_verify_tmp"
TMP_DOC_ID = 987654
ALIAS = "milvus_verify"

RESULTS: List[Dict[str, str]] = []


# ----------------------------------------------------------------------
# 结果记录与断言
# ----------------------------------------------------------------------

class CheckFailure(AssertionError):
    """单条检查失败。"""


def record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append({"status": status, "name": name, "detail": detail})
    suffix = f"  — {detail}" if detail else ""
    print(f"[{status:4s}] {name}{suffix}", flush=True)


def check(condition: bool, name: str, detail: str = "") -> None:
    if condition:
        record("PASS", name, detail)
    else:
        record("FAIL", name, detail)
        raise CheckFailure(f"{name}: {detail}")


def skip(name: str, detail: str = "") -> None:
    record("SKIP", name, detail)


# ----------------------------------------------------------------------
# HTTP 辅助
# ----------------------------------------------------------------------

def post_json(path: str, payload: Dict[str, Any]) -> Tuple[int, Any]:
    import httpx

    resp = httpx.post(f"{API_BASE_URL}{path}", json=payload, timeout=TIMEOUT)
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001 - 非 JSON 响应按文本返回
        return resp.status_code, resp.text


def get_json(path: str) -> Tuple[int, Any]:
    import httpx

    resp = httpx.get(f"{API_BASE_URL}{path}", timeout=TIMEOUT)
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code, resp.text


def delete_json(path: str) -> Tuple[int, Any]:
    import httpx

    resp = httpx.delete(f"{API_BASE_URL}{path}", timeout=TIMEOUT)
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code, resp.text


# ----------------------------------------------------------------------
# 1. pymilvus 客户端 + server 连接
# ----------------------------------------------------------------------

def connect_milvus() -> Any:
    try:
        from pymilvus import connections, utility, __version__ as pymilvus_version
    except ImportError as exc:  # pragma: no cover - 依赖/环境问题
        print(
            f"[FATAL] pymilvus 导入失败: {exc}\n"
            "  提示：pymilvus 2.5.4 仍依赖 pkg_resources，而 setuptools>=81 已移除该模块。\n"
            "  修复：pip install 'setuptools<81'（如 setuptools==80.9.0），或使用项目 venv/镜像。",
            flush=True,
        )
        raise SystemExit(2)

    print(f"pymilvus 客户端版本: {pymilvus_version}", flush=True)
    t0 = time.time()
    connections.connect(alias=ALIAS, host=MILVUS_HOST, port=MILVUS_PORT, timeout=10)
    connect_cost = time.time() - t0
    server_version = utility.get_server_version(using=ALIAS)
    check(True, "pymilvus 连接 Milvus", f"{MILVUS_HOST}:{MILVUS_PORT}, 耗时 {connect_cost:.2f}s")
    record("INFO", "服务端版本", server_version)
    record("INFO", "已有 collections", str(utility.list_collections(using=ALIAS)))
    return server_version


# ----------------------------------------------------------------------
# 2. 临时 collection 全链路（create → insert → flush → search → delete → drop）
# ----------------------------------------------------------------------

def _load_embedder() -> Tuple[Any, str]:
    """优先复用后端 EmbeddingService（HashingEmbedder），失败则随机单位向量兜底。"""
    try:
        from app.services.knowledge.embedding import get_embedder

        embedder = get_embedder()
        dim = int(embedder.dimension)
        return embedder, f"{type(embedder).__name__}(dim={dim})"
    except Exception as exc:  # noqa: BLE001 - 脚本允许无后端依赖运行
        print(f"[WARN] 后端 EmbeddingService 不可用（{exc}），改用随机单位向量。", flush=True)

        class _RandomEmbedder:
            dimension = DIM

            def embed(self, text: str) -> List[float]:
                import random

                vec = [random.gauss(0, 1) for _ in range(DIM)]
                norm = sum(v * v for v in vec) ** 0.5 or 1.0
                return [v / norm for v in vec]

            def embed_batch(self, texts: List[str]) -> List[List[float]]:
                return [self.embed(t) for t in texts]

        return _RandomEmbedder(), f"RandomEmbedder(dim={DIM})"


def verify_collection_roundtrip() -> None:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        utility,
    )

    embedder, provider_desc = _load_embedder()
    emb = embedder.embed("USB 设备超时")
    check(
        len(emb) == DIM,
        "embedding 维度与 MILVUS_DIM 一致",
        f"{provider_desc}, dim={len(emb)}",
    )

    # 幂等：先清理上次残留
    if utility.has_collection(TMP_COLLECTION, using=ALIAS):
        utility.drop_collection(TMP_COLLECTION, using=ALIAS)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
        FieldSchema(name="doc_id", dtype=DataType.INT64),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2000),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIM),
    ]
    collection = Collection(TMP_COLLECTION, schema=CollectionSchema(fields), using=ALIAS)
    try:
        index_params = {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        }
        collection.create_index("embedding", index_params)
        collection.load()
        record("PASS", "创建临时 collection + IVF_FLAT/IP 索引", TMP_COLLECTION)

        texts = [
            "USB 设备超时无响应，检查线缆与驱动",
            "磁盘空间不足导致服务崩溃",
            "数据库连接池耗尽，请求超时",
        ]
        vectors = embedder.embed_batch(texts)
        check(len(vectors) == 3 and all(len(v) == DIM for v in vectors),
              "批量生成 512 维向量", f"{len(vectors)} 条")

        ids = [TMP_DOC_ID * 10000 + i for i in range(len(texts))]
        doc_ids = [TMP_DOC_ID] * len(texts)
        collection.insert([ids, doc_ids, texts, vectors])
        collection.flush()
        check(collection.num_entities >= 3, "insert + flush", f"num_entities={collection.num_entities}")

        query_vec = embedder.embed("USB 超时")
        hits = collection.search(
            data=[query_vec],
            anns_field="embedding",
            param={"metric_type": "IP", "params": {"nprobe": 16}},
            limit=3,
            output_fields=["doc_id", "content"],
        )[0]
        hit_desc = ", ".join(
            f"id={h.id} doc_id={h.entity.get('doc_id')} score={float(h.score):.6f}" for h in hits
        )
        check(len(hits) > 0, "search 命中", hit_desc)
        check(
            hits[0].entity.get("doc_id") == TMP_DOC_ID,
            "search Top1 命中目标文档",
            f"doc_id={hits[0].entity.get('doc_id')}, score={float(hits[0].score):.6f}",
        )

        # delete 表达式 + query 验证（注意：num_entities 在 delete 后不会立即下降，
        # 属于 Milvus 统计口径，需用 query 验证真实删除）
        collection.delete(f"doc_id == {TMP_DOC_ID}")
        collection.flush()
        remain = collection.query(f"doc_id == {TMP_DOC_ID}", output_fields=["id"])
        check(len(remain) == 0, "delete 表达式删除并 query 确认", f"剩余 {len(remain)} 条")
    finally:
        utility.drop_collection(TMP_COLLECTION, using=ALIAS)
        record("PASS", "drop 临时 collection（清理完成）", TMP_COLLECTION)


# ----------------------------------------------------------------------
# 3. 业务 collection knowledge_docs 状态
# ----------------------------------------------------------------------

def verify_knowledge_collection() -> None:
    from pymilvus import Collection, utility

    if not utility.has_collection("knowledge_docs", using=ALIAS):
        skip("knowledge_docs collection", "尚未创建（后端首次成功连接 Milvus 时会自动建表）")
        return

    collection = Collection("knowledge_docs", using=ALIAS)
    dim = None
    for field in collection.schema.fields:
        if field.name == "embedding":
            dim = int(field.params.get("dim", 0))
    record("INFO", "knowledge_docs", f"num_entities={collection.num_entities}, embedding_dim={dim}")
    check(dim == DIM, "knowledge_docs 向量维度与配置一致", f"dim={dim}, 期望={DIM}")
    if collection.num_entities == 0:
        record("INFO", "knowledge_docs 当前为空", "实体数 > 0 的断言在 API 索引测试后执行")


# ----------------------------------------------------------------------
# 4. 后端 HTTP API 端到端
# ----------------------------------------------------------------------

def _try_delete_test_doc() -> None:
    try:
        status, body = delete_json(f"/api/v1/vector/index/{TMP_DOC_ID}")
        print(f"  cleanup DELETE /api/v1/vector/index/{TMP_DOC_ID} -> {status} {body}", flush=True)
    except Exception as exc:  # noqa: BLE001 - 清理失败不阻塞结论
        print(f"  [WARN] 清理测试向量失败: {exc}", flush=True)


def verify_api() -> None:
    import httpx

    try:
        status, body = get_json("/health")
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        skip("后端 API 端到端", f"服务不可达（{exc.__class__.__name__}），跳过")
        return

    check(status == 200, "GET /health", f"HTTP {status}")

    # ── 1) 向量服务健康检查（注意：该路由是 GET，不是 POST）──
    status, body = get_json("/api/v1/vector/health")
    print(f"  GET /api/v1/vector/health -> {status} {body}", flush=True)
    check(status == 200, "GET /api/v1/vector/health 返回 200", f"HTTP {status}")
    check(bool(body.get("milvus_available")), "milvus_available=true",
          f"milvus_available={body.get('milvus_available')}, "
          f"collection={body.get('collection')}, "
          f"embedding_provider={body.get('embedding_provider')}")
    # /health 返回的是 EmbeddingService 包装类名（内部激活 HashingEmbedder），
    # 二者都表示本地嵌入链路可用。
    provider = str(body.get("embedding_provider"))
    check(provider in ("HashingEmbedder", "EmbeddingService"),
          "embedding_provider 为本地嵌入（HashingEmbedder/EmbeddingService）", provider)

    # ── 2) Embedding ──
    status, body = post_json("/api/v1/vector/embed", {"text": "USB 设备超时"})
    print(f"  POST /api/v1/vector/embed -> {status} dimension={body.get('dimension')} "
          f"norm={body.get('norm'):.6f}" if isinstance(body, dict) and "dimension" in body
          else f"  POST /api/v1/vector/embed -> {status} {body}", flush=True)
    check(status == 200, "POST /api/v1/vector/embed 返回 200", f"HTTP {status}")
    check(body.get("dimension") == DIM, "embed dimension=512", str(body.get("dimension")))

    # ── 3) index → search（纯向量）──
    _try_delete_test_doc()
    content = "USB 设备超时无响应，检查线缆与驱动"
    status, body = post_json(
        "/api/v1/vector/index", {"doc_id": TMP_DOC_ID, "content": content}
    )
    print(f"  POST /api/v1/vector/index -> {status} {body}", flush=True)
    check(status == 200, "POST /api/v1/vector/index 返回 200", f"HTTP {status}")
    check(int(body.get("chunks_indexed", 0)) > 0, "chunks_indexed>0",
          f"chunks_indexed={body.get('chunks_indexed')}, message={body.get('message')}")

    status, body = post_json(
        "/api/v1/vector/search",
        {"query": "USB 超时", "top_k": 5, "use_hybrid": False},
    )
    print(f"  POST /api/v1/vector/search (use_hybrid=false) -> {status} {body}", flush=True)
    check(status == 200, "POST /api/v1/vector/search 返回 200", f"HTTP {status}")
    check(body.get("strategy") == "vector_only", "strategy=vector_only", str(body.get("strategy")))
    check(int(body.get("total_hits", 0)) > 0, "纯向量搜索有命中", f"total_hits={body.get('total_hits')}")
    results = body.get("results") or []
    if results:
        top = results[0]
        print(f"  Top1: id={top.get('id')} score={top.get('score')} snippet={str(top.get('snippet'))[:60]}",
              flush=True)
        check(top.get("id") == TMP_DOC_ID, "纯向量搜索 Top1 命中测试文档",
              f"id={top.get('id')}, score={top.get('score')}")

    # ── 4) pymilvus 侧确认真实写入 knowledge_docs ──
    try:
        from pymilvus import Collection

        collection = Collection("knowledge_docs", using=ALIAS)
        collection.load()
        rows = collection.query(f"doc_id == {TMP_DOC_ID}", output_fields=["id", "doc_id"])
        check(len(rows) > 0, "knowledge_docs 中可查到测试向量", f"{len(rows)} 条")
        record("INFO", "knowledge_docs 实体数", str(collection.num_entities))
        check(collection.num_entities > 0, "knowledge_docs 实体数 > 0",
              f"num_entities={collection.num_entities}")
    except Exception as exc:  # noqa: BLE001 - Milvus 侧查询失败记为 FAIL
        record("FAIL", "knowledge_docs 中可查到测试向量", str(exc))

    # ── 5) 混合搜索（仅记录 strategy：可能为 hybrid，也可能因 BM25/关键词侧为空而回退）──
    status, body = post_json(
        "/api/v1/vector/search",
        {"query": "USB 超时", "top_k": 5, "use_hybrid": True},
    )
    print(f"  POST /api/v1/vector/search (use_hybrid=true) -> {status} "
          f"strategy={body.get('strategy')} total_hits={body.get('total_hits')}", flush=True)
    check(status == 200, "混合搜索 API 返回 200", f"HTTP {status}")
    check(body.get("strategy") in ("hybrid", "vector_only", "keyword_only"),
          "混合搜索返回合法 strategy", str(body.get("strategy")))

    # ── 6) 清理测试向量 ──
    _try_delete_test_doc()


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Milvus 真实链路端到端验证")
    parser.add_argument("--skip-api", action="store_true", help="只跑 pymilvus 直连，不测后端 API")
    args = parser.parse_args()

    print("=" * 78, flush=True)
    print("Milvus 真实链路验证 | "
          f"server={MILVUS_HOST}:{MILVUS_PORT} dim={DIM} api={API_BASE_URL}", flush=True)
    print("=" * 78, flush=True)

    try:
        connect_milvus()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - 连接失败给出明确退出码
        print(f"[FATAL] 无法连接 Milvus {MILVUS_HOST}:{MILVUS_PORT}: {exc}", flush=True)
        return 2

    failures = 0
    try:
        verify_collection_roundtrip()
    except CheckFailure:
        failures += 1
    except Exception as exc:  # noqa: BLE001 - 未预期异常也记为失败
        record("FAIL", "临时 collection 全链路", f"{exc.__class__.__name__}: {exc}")
        failures += 1

    try:
        verify_knowledge_collection()
    except CheckFailure:
        failures += 1
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "knowledge_docs 检查", f"{exc.__class__.__name__}: {exc}")
        failures += 1

    if args.skip_api:
        skip("后端 API 端到端", "--skip-api")
    else:
        try:
            verify_api()
        except CheckFailure:
            failures += 1
        except Exception as exc:  # noqa: BLE001
            record("FAIL", "后端 API 端到端", f"{exc.__class__.__name__}: {exc}")
            failures += 1

    # 汇总
    total = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("PASS", "FAIL", "SKIP", "INFO")}
    print("-" * 78, flush=True)
    print(f"汇总: PASS={total['PASS']} FAIL={total['FAIL']} SKIP={total['SKIP']} INFO={total['INFO']}",
          flush=True)
    for r in RESULTS:
        if r["status"] == "FAIL":
            print(f"  FAIL: {r['name']} — {r['detail']}", flush=True)
    print("-" * 78, flush=True)

    if total["FAIL"] > 0:
        print("结论: FAIL（存在未通过检查）", flush=True)
        return 1
    print("结论: PASS（真实向量链路验证通过）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
