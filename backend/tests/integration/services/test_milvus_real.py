"""Milvus 真实服务集成测试（默认跳过）。

门槛与行为：
- 默认 skip：仅当环境变量 ``RUN_REAL_MILVUS=1`` 时执行（避免默认全量 pytest 依赖外部服务）；
- 自动 skip：pymilvus 不可导入（如缺 setuptools<81 导致 pkg_resources 缺失）或
  Milvus 不可连接（localhost:19530）时，模块内各测试 skip 而非失败；
- 自清理：临时 collection 用随机名，测试结束在 finally 中 drop；不触碰 knowledge_docs 数据。

运行方式::

    # 本机 Milvus 已启动（deploy/docker-compose.yml 的 milvus 服务）
    cd backend
    RUN_REAL_MILVUS=1 python -m pytest tests/integration/services/test_milvus_real.py -v

环境变量：
    RUN_REAL_MILVUS  设为 1 才执行
    MILVUS_HOST      默认 localhost
    MILVUS_PORT      默认 19530
    MILVUS_DIM       默认 512
"""

from __future__ import annotations

import os
import random
import uuid
from typing import List

import pytest

# 默认跳过（防止默认全量 pytest 依赖 Milvus / 污染基线）
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_MILVUS") != "1",
    reason="真实 Milvus 集成测试默认跳过；设置 RUN_REAL_MILVUS=1 且 Milvus 在 "
    "localhost:19530 时启用",
)

# pymilvus 导入失败（例如 setuptools>=81 移除 pkg_resources）时模块仍可正常
# collect，由 fixture 统一 skip，避免整个测试会话 collection error。
_pymilvus_import_error: Exception | None = None
try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )
except ImportError as exc:  # noqa: BLE001 - 记为 skip 原因
    _pymilvus_import_error = exc

MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = str(os.getenv("MILVUS_PORT", "19530"))
MILVUS_DIM = int(os.getenv("MILVUS_DIM", "512") or 512)
ALIAS = "pytest_real_milvus"


def _unit_vector(rng: random.Random) -> List[float]:
    """生成确定性随机单位向量（避免依赖 embedding 模型/网络）。"""
    vec = [rng.gauss(0.0, 1.0) for _ in range(MILVUS_DIM)]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


@pytest.fixture(scope="module")
def milvus_conn():
    """连接真实 Milvus；不可连接时整组测试自动 skip。"""
    if _pymilvus_import_error is not None:
        pytest.skip(f"pymilvus 不可导入（{_pymilvus_import_error}）——请检查 setuptools<81")
    try:
        connections.connect(alias=ALIAS, host=MILVUS_HOST, port=MILVUS_PORT, timeout=5)
        utility.get_server_version(using=ALIAS)
    except Exception as exc:  # noqa: BLE001 - 服务未启动时跳过
        pytest.skip(f"Milvus {MILVUS_HOST}:{MILVUS_PORT} 不可连接: {exc}")
    try:
        yield ALIAS
    finally:
        try:
            connections.disconnect(ALIAS)
        except Exception:  # noqa: BLE001 - 清理阶段忽略
            pass


@pytest.fixture(scope="module")
def temp_collection(milvus_conn):
    """创建独立的临时 collection（dim=MILVUS_DIM），结束后 drop。"""
    name = f"milvus_pytest_{uuid.uuid4().hex[:8]}"
    if utility.has_collection(name, using=milvus_conn):
        utility.drop_collection(name, using=milvus_conn)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
        FieldSchema(name="doc_id", dtype=DataType.INT64),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2000),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=MILVUS_DIM),
    ]
    collection = Collection(
        name, schema=CollectionSchema(fields), using=milvus_conn
    )
    collection.create_index(
        "embedding",
        {"metric_type": "IP", "index_type": "IVF_FLAT", "params": {"nlist": 128}},
    )
    collection.load()
    try:
        yield collection
    finally:
        try:
            utility.drop_collection(name, using=milvus_conn)
        except Exception:  # noqa: BLE001 - 清理失败不掩盖测试结果
            pass


# ----------------------------------------------------------------------
# 测试
# ----------------------------------------------------------------------

def test_real_connection(milvus_conn):
    """pymilvus 能真实连接 server 并读取版本/collection 列表。"""
    server_version = utility.get_server_version(using=milvus_conn)
    assert server_version, "server version 不应为空"
    assert isinstance(utility.list_collections(using=milvus_conn), list)


def test_insert_flush_search_and_cleanup(temp_collection, milvus_conn):
    """真实链路：insert → flush → search 命中自身 → delete 表达式 → query 确认删除。"""
    collection = temp_collection
    rng = random.Random(20261112)
    vectors = [_unit_vector(rng) for _ in range(3)]
    assert all(len(v) == MILVUS_DIM for v in vectors)

    ids = [990001, 990002, 990003]
    doc_ids = [987654, 987655, 987656]
    contents = ["USB 设备超时", "磁盘空间不足", "数据库连接超时"]
    collection.insert([ids, doc_ids, contents, vectors])
    collection.flush()
    assert collection.num_entities >= 3

    hits = collection.search(
        data=[vectors[0]],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 16}},
        limit=3,
        output_fields=["doc_id", "content"],
    )[0]
    assert len(hits) > 0, "search 应至少命中 1 条"
    assert hits[0].entity.get("doc_id") == 987654, "Top1 应命中自身文档"
    assert float(hits[0].score) > 0.99, "自身向量 IP 相似度应接近 1.0"

    # delete 表达式 + query 验证（num_entities 在 delete 后不立即下降，属 Milvus 统计口径）
    collection.delete("doc_id == 987654")
    collection.flush()
    remain = collection.query("doc_id == 987654", output_fields=["id"])
    assert remain == [], f"删除后应查不到该 doc，实际 {remain}"


def test_knowledge_docs_collection_if_present(milvus_conn):
    """业务 collection knowledge_docs 若已由后端创建，则实体数应 > 0。"""
    if not utility.has_collection("knowledge_docs", using=milvus_conn):
        pytest.skip("knowledge_docs 尚未创建（后端未以 Milvus 可用状态启动过）")

    collection = Collection("knowledge_docs", using=milvus_conn)

    # 兼容旧版本 bug 遗留的「已创建但无索引」collection：Milvus 2.4+ 无索引
    # load 会报 code=700 index not found，此时跳过而非误报失败。
    has_embedding_index = False
    for index in collection.indexes:
        field_name = getattr(index, "field_name", None)
        if field_name is None:
            field_name = (getattr(index, "params", None) or {}).get("field_name")
        if field_name == "embedding":
            has_embedding_index = True
            break
    if not has_embedding_index:
        pytest.skip("knowledge_docs 存在但缺少向量索引（旧版本创建的损坏状态）")

    collection.load()
    if collection.num_entities == 0:
        pytest.skip("knowledge_docs 已建表但尚无数据（后端尚未索引任何文档）")
    assert collection.num_entities > 0, "knowledge_docs 应至少包含 1 条实体"

    dim = None
    for field in collection.schema.fields:
        if field.name == "embedding":
            dim = int(field.params.get("dim", 0))
    assert dim == MILVUS_DIM, f"collection 维度 {dim} 应与配置 MILVUS_DIM={MILVUS_DIM} 一致"
