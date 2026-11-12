#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""BGE 本地嵌入真实链路端到端验证（下载 → 加载 → 语义质量 → 离线可复现 → Milvus 联合检索）。

===============================================================================
为什么需要这个脚本
===============================================================================
生产配置 ``EMBEDDING_PROVIDER=auto`` 时 BGE（``BAAI/bge-small-zh-v1.5``）是首选
嵌入器；而 ``huggingface.co`` 在国内通常不可直连，首次加载会超时并静默回退到
``HashingEmbedder``（词形哈希，非语义向量）。仅靠默认测试（conftest 强制
``EMBEDDING_PROVIDER=hash``）无法证明「BGE 实链路可用」。本脚本用真实下载的
模型权重，实测并打印整条链路的证据：

    1/5 下载/缓存核验：snapshot_download（hf-mirror）→ commit / 文件清单 / 体积 / SHA256
    2/5 真实加载：BGEEmbedder 按 repo id 加载 → dimension=512、冷/热加载耗时
    3/5 语义质量：中文样本对余弦相似度排序、归一化 norm≈1、batch 与单条一致、CPU 耗时
    4/5 离线可复现：HF_HUB_OFFLINE=1 + 无效 HF_ENDPOINT 的子进程仍能按 repo id 加载
    5/5 Milvus 联合检索（可选，Milvus 可连时）：VectorService.index_document(9999)
        → search("USB 超时") 命中 doc 9999 → delete_document(9999) 清理

===============================================================================
环境变量（关键）
===============================================================================
``HF_ENDPOINT=https://hf-mirror.com``
    huggingface.co 被墙时的镜像端点。**必须在 import huggingface_hub /
    sentence_transformers 之前设置**（脚本检测到未设置时会自动补默认值，但若你的
    环境只能用其它镜像，请显式设置后运行）。

``HF_HUB_OFFLINE=1``（配合 ``TRANSFORMERS_OFFLINE=1``）
    强制离线模式：只读本地缓存、不访问网络。脚本第 4 阶段用子进程验证它。

    注意：``HF_HUB_OFFLINE`` 由 huggingface_hub 在 **import 时**读取常量，
    因此运行中改 os.environ 不会生效——必须在新进程里设置（脚本内已如此实现）。

``EMBEDDING_LOAD_TIMEOUT``
    后端 ``EmbeddingService._try_bge()`` 的加载超时（默认 30s）。CPU 冷加载通常
    3-20s，但容器/低配机器可能更久，Docker 部署建议调到 120s+。本脚本第 5 阶段
    会把 ``VectorService._EMBEDDING_LOAD_TIMEOUT`` 临时调大以免误判不可用。

===============================================================================
用法（在 backend/ 目录下执行；Windows PowerShell）
===============================================================================
# 0) 一次性安装（本地 BGE 依赖，约 2GB+，见 backend/requirements-ml.txt）
pip install -r requirements-ml.txt

# 1) 在线全链路（下载 + 加载 + 语义 + 离线子进程 + Milvus）；首次运行
#    下载约 90MB；本机 torch import 冷启动可能需要数分钟，请耐心等待
$env:HF_ENDPOINT='https://hf-mirror.com'
..\.venv\Scripts\python.exe -X utf8 scripts\verify\bge_embedding_e2e.py `
    --log-file ..\bge_e2e_run.log

# 2) 已缓存后只做加载+语义（跳过下载，秒开）
..\.venv\Scripts\python.exe -X utf8 scripts\verify\bge_embedding_e2e.py --skip-download

# 3) 纯离线部署验证（不访问网络；需模型已缓存）
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
..\.venv\Scripts\python.exe -X utf8 scripts\verify\bge_embedding_e2e.py --offline

# 4) 跳过 Milvus（Milvus 未启动 / 只想验证模型本身）
..\.venv\Scripts\python.exe -X utf8 scripts\verify\bge_embedding_e2e.py --milvus off

# 5) 只验证缓存与下载（不 import torch，便于没装 ML 依赖时排查网络）
..\.venv\Scripts\python.exe -X utf8 scripts\verify\bge_embedding_e2e.py --stages cache

退出码：0=全部通过；1=有检查项失败；2=致命错误（下载/加载失败，后续阶段无法执行）。

===============================================================================
Docker 部署提示
===============================================================================
- ``backend/Dockerfile`` 默认**不安装** torch / sentence-transformers（见
  ``requirements-ml.txt`` 与 Dockerfile builder 阶段注释），生产默认走云端
  Embedding；要启用本地 BGE 需在镜像构建时取消 ``requirements-ml.txt`` 的注释，
  或在容器内 ``pip install -r requirements-ml.txt``（镜像体积 +2GB 左右）。
- 模型缓存不要打进镜像：把宿主机的 ``%USERPROFILE%\\.cache\\huggingface``
  挂载到容器 ``/root/.cache/huggingface``（只读即可），并设置
  ``HF_HUB_OFFLINE=1``，避免容器首次启动时联网下载。
- ``EMBEDDING_LOAD_TIMEOUT`` 建议设为 120（秒）；否则冷启动 + CPU 加载慢时
  EmbeddingService 会超时回退到 hash 嵌入，检索质量静默下降。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 常量：路径 / 模型 / 镜像端点
# ---------------------------------------------------------------------------
SCRIPT_PATH = Path(__file__).resolve()
BACKEND_DIR = SCRIPT_PATH.parents[2]  # backend/
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"

STAGE_CACHE = "cache"
STAGE_LOAD = "load"
STAGE_SEMANTIC = "semantic"
STAGE_OFFLINE = "offline"
STAGE_MILVUS = "milvus"
ALL_STAGES = [STAGE_CACHE, STAGE_LOAD, STAGE_SEMANTIC, STAGE_OFFLINE, STAGE_MILVUS]

# 语义质量样本：每组 = 一条查询句 + 一条语义相近句 + 一条语义无关句
SEMANTIC_GROUPS: List[Dict[str, Any]] = [
    {
        "topic": "USB 超时",
        "query": "USB 设备超时无响应",
        "similar": "USB 接口通信超时",
        "dissimilar": "磁盘空间不足导致服务崩溃",
    },
    {
        "topic": "内核 panic",
        "query": "内核 panic 导致系统重启",
        "similar": "Kernel panic 触发系统崩溃重启",
        "dissimilar": "数据库连接池耗尽导致请求失败",
    },
    {
        "topic": "网络丢包",
        "query": "网络丢包严重导致通信中断",
        "similar": "网卡丢包引起数据传输中断",
        "dissimilar": "内存 OOM 导致服务进程被杀死",
    },
    {
        "topic": "内存 OOM",
        "query": "内存 OOM 导致服务进程被杀死",
        "similar": "内存溢出 OutOfMemory 进程崩溃",
        "dissimilar": "USB 设备超时无响应",
    },
]

# 单条 / 批量耗时测试用文本（全部唯一，避免命中缓存）
LATENCY_TEXTS = [
    "USB 设备超时无响应，请检查线缆与驱动",
    "内核 panic 后系统自动重启",
    "网络拥塞导致大量丢包",
    "内存不足触发 OOM Killer",
    "磁盘 I/O 错误导致文件系统只读",
    "数据库连接超时",
    "Wi-Fi 信号弱导致频繁掉线",
    "服务启动失败，端口被占用",
]


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
class _Tee:
    """同时写多个流的简易 tee（用于 --log-file 保留 UTF-8 完整日志）。"""

    def __init__(self, *streams: Any) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            try:
                stream.write(data)
                stream.flush()
            except Exception:  # noqa: BLE001 - 日志写出失败不应影响验证
                pass
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:  # noqa: BLE001
                pass

    def isatty(self) -> bool:
        return False


def _fmt_bytes(num: int) -> str:
    return f"{num / (1024 * 1024):.2f} MiB"


def _fmt_secs(seconds: float) -> str:
    if seconds >= 60:
        return f"{seconds:.1f}s ({seconds / 60:.2f}min)"
    return f"{seconds:.2f}s"


def _section(index: int, total: int, title: str) -> None:
    print()
    print("=" * 78)
    print(f"[{index}/{total}] {title}")
    print("=" * 78, flush=True)


def _ok(label: str, detail: Any = "") -> None:
    print(f"  [PASS] {label}" + (f" → {detail}" if detail else ""), flush=True)


def _fail(label: str, detail: Any = "") -> None:
    print(f"  [FAIL] {label}" + (f" → {detail}" if detail else ""), flush=True)


def _info(label: str, detail: Any = "") -> None:
    print(f"  [INFO] {label}" + (f" → {detail}" if detail else ""), flush=True)


def _cosine(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    dot = math.fsum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(math.fsum(a * a for a in vec_a))
    norm_b = math.sqrt(math.fsum(b * b for b in vec_b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _norm(vec: Sequence[float]) -> float:
    return math.sqrt(math.fsum(v * v for v in vec))


def _hub_cache_dir() -> Path:
    """复刻 huggingface_hub.constants.HF_HUB_CACHE 的推导逻辑（不 import 它）。"""
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


def _repo_cache_dir(model: str = MODEL_NAME) -> Path:
    return _hub_cache_dir() / ("models--" + model.replace("/", "--"))


def _read_ref_commit(repo_dir: Path) -> Optional[str]:
    ref = repo_dir / "refs" / "main"
    try:
        text = ref.read_text(encoding="utf-8").strip()
        return text or None
    except OSError:
        return None


def _weight_files(snapshot: Path) -> List[Path]:
    return [
        p
        for p in (snapshot / "model.safetensors", snapshot / "pytorch_model.bin")
        if p.is_file()
    ]


def _find_cached_snapshot(model: str = MODEL_NAME) -> Tuple[Optional[Path], Optional[str]]:
    """返回 (snapshot 目录, commit)。缓存不完整时返回 (None, None)。"""
    repo_dir = _repo_cache_dir(model)
    if not repo_dir.is_dir():
        return None, None
    commit = _read_ref_commit(repo_dir)
    candidates: List[Tuple[Path, Optional[str]]] = []
    if commit:
        candidates.append((repo_dir / "snapshots" / commit, commit))
    snapshots_dir = repo_dir / "snapshots"
    if snapshots_dir.is_dir():
        for child in sorted(snapshots_dir.iterdir()):
            if not child.is_dir():
                continue
            known = [(p, cm) for p, cm in candidates]
            if (child, child.name) not in known:
                candidates.append((child, child.name))
    for snapshot, cand_commit in candidates:
        if not (snapshot / "config.json").is_file():
            continue
        weights = _weight_files(snapshot)
        if not weights:
            continue
        if max(p.stat().st_size for p in weights) < 50 * 1024 * 1024:
            continue  # 不完整的权重（例如中断的下载）
        return snapshot, cand_commit
    return None, None


def _snapshot_files(snapshot: Path) -> List[Tuple[str, int]]:
    entries: List[Tuple[str, int]] = []
    for path in sorted(snapshot.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(snapshot))
            try:
                entries.append((rel, path.stat().st_size))
            except OSError:
                continue
    return entries


def _dir_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 环境准备（必须在任何 huggingface_hub / sentence_transformers / app import 之前）
# ---------------------------------------------------------------------------
def configure_env(args: argparse.Namespace) -> Dict[str, Any]:
    """按 CLI 参数设置环境变量，必须在 import 重依赖之前调用。

    huggingface_hub 在 import 时把 HF_ENDPOINT / HF_HUB_OFFLINE 固化为常量，
    因此这里统一在一次进程启动的最开始完成所有环境变量注入。
    """
    info: Dict[str, Any] = {}

    # --- HuggingFace 端点 / 离线模式 ---
    if args.offline_child or args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        info["offline"] = True
        if args.offline and not args.offline_child:
            # 父进程离线模式：清掉端点，证明加载完全走本地缓存
            os.environ.pop("HF_ENDPOINT", None)
    else:
        info["offline"] = False
        if args.endpoint is not None:
            if args.endpoint:
                os.environ["HF_ENDPOINT"] = args.endpoint
            else:
                os.environ.pop("HF_ENDPOINT", None)
        else:
            os.environ.setdefault("HF_ENDPOINT", DEFAULT_HF_ENDPOINT)

    info["HF_ENDPOINT"] = os.environ.get("HF_ENDPOINT", "")
    info["HF_HUB_OFFLINE"] = os.environ.get("HF_HUB_OFFLINE", "")
    info["TRANSFORMERS_OFFLINE"] = os.environ.get("TRANSFORMERS_OFFLINE", "")

    # --- Milvus 联合检索：在 import app.core.config（settings 单例）之前注入 ---
    milvus_mode = args.milvus
    if args.offline_child:
        # 离线子进程只验证模型加载，不碰 Milvus（也避免额外 2s 探测）
        info["milvus_probe"] = False
        info["milvus_env_enabled"] = False
        backend_str = str(BACKEND_DIR)
        if backend_str not in sys.path:
            sys.path.insert(0, backend_str)
        info["backend_dir"] = backend_str
        return info

    milvus_reachable = _tcp_probe(
        os.environ.get("MILVUS_HOST", "localhost"),
        int(os.environ.get("MILVUS_PORT", "19530") or 19530),
        timeout=2.0,
    )
    info["milvus_probe"] = milvus_reachable
    if milvus_mode != "off" and milvus_mode != "skip":
        if milvus_mode == "on" or (milvus_mode == "auto" and milvus_reachable):
            os.environ["MILVUS_ENABLED"] = "true"
            os.environ.setdefault("EMBEDDING_PROVIDER", "local")
            os.environ.setdefault("EMBEDDING_DIM", "512")
            os.environ.setdefault("MILVUS_HOST", "localhost")
            os.environ.setdefault("MILVUS_PORT", "19530")
            os.environ.setdefault("MILVUS_DIM", "512")
            # 加载超时调大，避免 CPU 冷加载被误判为不可用
            os.environ.setdefault("EMBEDDING_LOAD_TIMEOUT", "300")
            # 验证环境必须「硬失败」而不是静默回退 hash
            os.environ.setdefault("EMBEDDING_HASH_FALLBACK", "false")
            info["milvus_env_enabled"] = True
        else:
            info["milvus_env_enabled"] = False
    else:
        info["milvus_env_enabled"] = False

    # 保证 backend/ 在 sys.path，便于 import app.*
    backend_str = str(BACKEND_DIR)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)
    info["backend_dir"] = backend_str
    return info


# ---------------------------------------------------------------------------
# 阶段 1：下载 / 缓存核验
# ---------------------------------------------------------------------------
def _cache_meta(snapshot: Optional[Path], commit: Optional[str], model: str) -> Dict[str, Any]:
    """收集模型缓存证据（文件清单、体积、权重 SHA256 等）。"""
    repo_dir = _repo_cache_dir(model)
    meta: Dict[str, Any] = {
        "model": model,
        "cache_root": str(_hub_cache_dir()),
        "repo_cache_dir": str(repo_dir),
        "snapshot_dir": str(snapshot) if snapshot else None,
        "commit": commit,
        "refs_main": _read_ref_commit(repo_dir),
    }
    if snapshot is None:
        return meta

    files = _snapshot_files(snapshot)
    meta["files"] = [{"name": name, "bytes": size} for name, size in files]
    meta["file_count"] = len(files)
    meta["snapshot_bytes"] = sum(size for _name, size in files)

    blobs_dir = repo_dir / "blobs"
    meta["blob_store_bytes"] = _dir_bytes(blobs_dir) if blobs_dir.is_dir() else 0
    meta["repo_disk_bytes"] = _dir_bytes(repo_dir) if repo_dir.is_dir() else 0

    # 权重文件 SHA256（默认 90MB 级，约 0.3s）
    weights = _weight_files(snapshot)
    meta["weights"] = []
    for weight in weights:
        entry: Dict[str, Any] = {
            "name": str(weight.relative_to(snapshot)),
            "bytes": weight.stat().st_size,
        }
        try:
            entry["sha256"] = _sha256(weight)
        except OSError as exc:  # noqa: BLE001
            entry["sha256_error"] = str(exc)
        meta["weights"].append(entry)

    # config.json 信息（hidden_size 应等于 512）
    try:
        cfg = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
        meta["config"] = {
            "architectures": cfg.get("architectures"),
            "hidden_size": cfg.get("hidden_size"),
            "model_type": cfg.get("model_type"),
            "max_position_embeddings": cfg.get("max_position_embeddings"),
            "vocab_size": cfg.get("vocab_size"),
        }
        meta["sentence_transformers_layout"] = (snapshot / "modules.json").is_file()
    except (OSError, ValueError) as exc:  # noqa: BLE001
        meta["config_error"] = str(exc)
    return meta


def _print_cache_meta(meta: Dict[str, Any]) -> None:
    _info("模型", meta.get("model"))
    _info("HF 缓存根目录", meta.get("cache_root"))
    _info("模型 repo 缓存", meta.get("repo_cache_dir"))
    _info("snapshot 目录", meta.get("snapshot_dir"))
    _info("commit", meta.get("commit"))
    if meta.get("file_count") is not None:
        _info("文件数 / snapshot 体积", f"{meta['file_count']} 个 / {_fmt_bytes(meta['snapshot_bytes'])}")
        _info("HF blobs 存储", _fmt_bytes(meta.get("blob_store_bytes", 0)))
        _info("repo 目录磁盘占用", _fmt_bytes(meta.get("repo_disk_bytes", 0)))
        print("  文件清单（snapshot）：")
        for entry in sorted(meta.get("files", []), key=lambda x: -x["bytes"]):
            print(f"    {entry['bytes']:>12,}  {_fmt_bytes(entry['bytes']):>10}  {entry['name']}")
    for weight in meta.get("weights", []):
        print(f"  权重 {weight['name']}: {weight['bytes']:,} bytes  sha256={weight.get('sha256', weight.get('sha256_error'))}")
    if "config" in meta:
        _info("config.json", json.dumps(meta["config"], ensure_ascii=False))
        _info("sentence-transformers 布局", meta.get("sentence_transformers_layout"))


def phase_cache(args: argparse.Namespace) -> Tuple[Optional[Path], Optional[str], Dict[str, Any], List[str]]:
    """阶段 1：真实下载（或核验已缓存），返回 snapshot 目录与证据。"""
    failures: List[str] = []
    _section(1, 5, "下载 / 缓存核验（hf-mirror → 本地 HF 缓存）")

    if not importlib.util.find_spec("huggingface_hub"):
        print("致命错误：未安装 huggingface_hub（本地 BGE 依赖见 requirements-ml.txt）")
        return None, None, {"error": "huggingface_hub not installed"}, ["huggingface_hub 未安装"]

    before_snapshot, before_commit = _find_cached_snapshot(args.model)
    was_cached = before_snapshot is not None
    _info("下载前缓存状态", f"已缓存（{before_commit}）" if was_cached else "未缓存，需要下载")

    if args.offline or args.skip_download:
        _info(
            "跳过网络下载，仅核验本地缓存",
            "原因: --offline" if args.offline else "原因: --skip-download",
        )
    else:
        try:
            import huggingface_hub
            from huggingface_hub import HfApi, snapshot_download

            _info("huggingface_hub 版本", huggingface_hub.__version__)
            _info("HF_ENDPOINT", os.environ.get("HF_ENDPOINT", "(未设置)"))
            print("  开始 snapshot_download（首次约 90MB；慢时请耐心等待）...", flush=True)
            started = time.perf_counter()
            snapshot_path = snapshot_download(repo_id=args.model, repo_type="model")
            elapsed = time.perf_counter() - started
            snapshot = Path(snapshot_path)
            commit = snapshot.name
            _ok("snapshot_download 成功", f"{_fmt_secs(elapsed)}")
            _info("下载耗时", f"{elapsed:.2f}s")
            _info("下载后缓存状态", "本次直接从缓存解析（模型此前已缓存）" if was_cached else "本次真实下载落盘")

            # commit 一致性：本地 refs/main 与远端 model_info（在线时）
            remote_sha: Optional[str] = None
            try:
                remote_sha = HfApi().model_info(repo_id=args.model).sha
                _info("远端 model_info commit", remote_sha)
                if remote_sha and commit and (remote_sha != commit):
                    failures.append(f"本地 commit({commit}) 与远端({remote_sha}) 不一致")
            except Exception as exc:  # noqa: BLE001 - 元数据失败不阻塞主链路
                _info("远端 model_info 获取失败（不影响加载）", str(exc))
            meta = _cache_meta(snapshot, commit, args.model)
            meta["download_elapsed_s"] = round(elapsed, 2)
            meta["downloaded_this_run"] = not was_cached
            meta["remote_commit"] = remote_sha
            _print_cache_meta(meta)
            return snapshot, commit, meta, failures
        except Exception as exc:  # noqa: BLE001 - 下载失败是致命错误
            _fail("snapshot_download 失败", exc)
            traceback.print_exc()
            failures.append(f"下载失败: {exc}")
            # 若本地其实已有完整缓存，则继续（离线可复现）
            cached, cached_commit = _find_cached_snapshot(args.model)
            if cached is not None:
                _info("检测到本地已有完整缓存，继续使用", cached_commit)
                meta = _cache_meta(cached, cached_commit, args.model)
                meta["download_error"] = str(exc)
                _print_cache_meta(meta)
                return cached, cached_commit, meta, failures
            return None, None, {"error": str(exc)}, failures

    # --offline 或 --skip-download：只核验缓存
    snapshot, commit = _find_cached_snapshot(args.model)
    if snapshot is None:
        _fail("本地模型缓存不存在或不完整", _repo_cache_dir(args.model))
        failures.append("模型未缓存（离线模式无法下载）")
        return None, None, {"error": "not cached"}, failures
    _ok("本地模型缓存完整", snapshot)
    meta = _cache_meta(snapshot, commit, args.model)
    meta["downloaded_this_run"] = False
    _print_cache_meta(meta)
    return snapshot, commit, meta, failures


# ---------------------------------------------------------------------------
# 阶段 2：真实加载
# ---------------------------------------------------------------------------
def phase_load(args: argparse.Namespace) -> Tuple[Any, Dict[str, Any], List[str]]:
    _section(2, 5, "真实加载（BGEEmbedder 按 repo id 加载，CPU）")
    failures: List[str] = []

    print("  import sentence-transformers / torch（首次在 Windows 上可能 5-10 分钟，", flush=True)
    print("  原因通常是杀毒软件实时扫描 torch 的 DLL；请耐心等待，不要中断）...", flush=True)
    # 先 import 轻量应用模块（出错可快速暴露），再触发 torch 重依赖导入
    from app.services.core.config import EmbeddingConfig
    from app.services.knowledge.embedding import BGEEmbedder

    started = time.perf_counter()
    import sentence_transformers  # noqa: F401 - 触发 torch 导入（耗时统计用）
    import_time = time.perf_counter() - started
    _info("sentence-transformers 版本", sentence_transformers.__version__)
    _info("import sentence_transformers 耗时", _fmt_secs(import_time))

    config = EmbeddingConfig(
        provider="local",
        model_name=args.model,
        device="cpu",
        normalize=True,
        dimension=512,
    )
    started = time.perf_counter()
    embedder = BGEEmbedder(config)
    cold_load = time.perf_counter() - started
    _info("冷加载（首次实例化，磁盘缓存已热）", _fmt_secs(cold_load))

    dim = embedder.dimension
    _info("模型维度", dim)
    if dim != 512:
        failures.append(f"dimension={dim}，预期 512")
        _fail("dimension 应为 512", dim)
    else:
        _ok("dimension=512")

    if not embedder.health_check():
        failures.append("health_check 失败")
        _fail("health_check")
    else:
        _ok("health_check 通过")

    started = time.perf_counter()
    _warm = BGEEmbedder(config)
    warm_load = time.perf_counter() - started
    _info("热加载（同进程第二次实例化）", _fmt_secs(warm_load))
    del _warm

    try:
        import torch

        _info("torch 版本", torch.__version__)
        _info("torch CPU 线程数", torch.get_num_threads())
        _info("torch 设备", "cpu")
    except Exception as exc:  # noqa: BLE001
        _info("torch 信息读取失败", str(exc))

    meta = {
        "sentence_transformers_version": sentence_transformers.__version__,
        "st_import_s": round(import_time, 2),
        "cold_load_s": round(cold_load, 2),
        "warm_load_s": round(warm_load, 2),
        "dimension": dim,
        "health_check": embedder.health_check(),
        "model_name": args.model,
    }
    return embedder, meta, failures


# ---------------------------------------------------------------------------
# 阶段 3：语义质量
# ---------------------------------------------------------------------------
def phase_semantic(embedder: Any) -> Tuple[Dict[str, Any], List[str]]:
    _section(3, 5, "语义质量（中文样本对余弦相似度 / 归一化 / batch 一致性 / CPU 耗时）")
    failures: List[str] = []

    # --- 3.1 语义相似度排序 ---
    print("  3.1 语义相似度排序（每组：相近句应显著高于无关句）")
    groups_result: List[Dict[str, Any]] = []
    for group in SEMANTIC_GROUPS:
        vec_query = embedder.embed(group["query"])
        vec_similar = embedder.embed(group["similar"])
        vec_dissimilar = embedder.embed(group["dissimilar"])
        sim_similar = _cosine(vec_query, vec_similar)
        sim_dissimilar = _cosine(vec_query, vec_dissimilar)
        delta = sim_similar - sim_dissimilar
        passed = sim_similar > sim_dissimilar
        entry = {
            "topic": group["topic"],
            "query": group["query"],
            "similar": group["similar"],
            "dissimilar": group["dissimilar"],
            "cos_similar": round(sim_similar, 4),
            "cos_dissimilar": round(sim_dissimilar, 4),
            "delta": round(delta, 4),
            "passed": passed,
        }
        groups_result.append(entry)
        marker = "PASS" if passed else "FAIL"
        print(
            f"    [{marker}] {group['topic']}: "
            f"cos(查询,相近)={sim_similar:.4f} vs cos(查询,无关)={sim_dissimilar:.4f} "
            f"(delta={delta:+.4f})"
        )
        if not passed:
            failures.append(f"语义排序错误: {group['topic']} 相近相似度未高于无关相似度")

    first = groups_result[0] if groups_result else None
    if first and first["passed"] and first["delta"] < 0.10:
        failures.append(
            f"USB 组区分度不足: delta={first['delta']:.4f} < 0.10（期望显著高于无关句）"
        )

    # --- 3.2 归一化 norm≈1 ---
    print("  3.2 归一化检查（BGEEmbedder.normalize=True → ||v||≈1.0）")
    norm_texts = [g["query"] for g in SEMANTIC_GROUPS]
    norms = [_norm(embedder.embed(text)) for text in norm_texts]
    max_norm_dev = max(abs(n - 1.0) for n in norms)
    _info("各样本向量 norm", [round(n, 6) for n in norms])
    if max_norm_dev < 1e-3:
        _ok("norm≈1.0", f"最大偏差 {max_norm_dev:.2e}")
    else:
        _fail("norm 偏差超过 1e-3", f"{max_norm_dev:.2e}")
        failures.append(f"归一化异常: max |norm-1|={max_norm_dev:.2e}")

    # --- 3.3 batch 与单条一致 ---
    print("  3.3 batch embed 与单条 embed 一致性（清空缓存后对比）")
    compare_texts = [g["query"] for g in SEMANTIC_GROUPS]
    _clear_embedder_cache(embedder)
    single_vecs = [embedder.embed(text) for text in compare_texts]
    _clear_embedder_cache(embedder)
    batch_vecs = embedder.embed_batch(compare_texts)
    max_abs_diff = max(
        abs(a - b) for sv, bv in zip(single_vecs, batch_vecs) for a, b in zip(sv, bv)
    )
    if max_abs_diff < 1e-5:
        _ok("batch 与单条一致", f"max|diff|={max_abs_diff:.2e}")
    else:
        _fail("batch 与单条不一致", f"max|diff|={max_abs_diff:.2e}")
        failures.append(f"batch/单条不一致 max|diff|={max_abs_diff:.2e}")

    # --- 3.4 CPU 耗时 ---
    print("  3.4 CPU 耗时（单条 vs 批量，缓存均已清空）")
    _clear_embedder_cache(embedder)
    started = time.perf_counter()
    embedder.embed(LATENCY_TEXTS[0])
    first_call = time.perf_counter() - started

    single_times: List[float] = []
    for text in LATENCY_TEXTS[:3]:
        _clear_embedder_cache(embedder)
        started = time.perf_counter()
        embedder.embed(text)
        single_times.append(time.perf_counter() - started)
    single_avg = sum(single_times) / len(single_times)

    _clear_embedder_cache(embedder)
    started = time.perf_counter()
    embedder.embed_batch(LATENCY_TEXTS)
    batch_total = time.perf_counter() - started
    batch_per_item = batch_total / len(LATENCY_TEXTS)

    _info("首次调用（含 warmup）", f"{first_call * 1000:.1f} ms")
    _info("单条 embed 平均（n=3）", f"{single_avg * 1000:.1f} ms/条")
    _info("batch embed 8 条", f"共 {batch_total * 1000:.1f} ms，{batch_per_item * 1000:.1f} ms/条")

    meta = {
        "semantic_groups": groups_result,
        "all_ordering_correct": all(g["passed"] for g in groups_result),
        "usb_delta": first["delta"] if first else None,
        "max_norm_deviation": float(f"{max_norm_dev:.3e}"),
        "batch_single_max_abs_diff": float(f"{max_abs_diff:.3e}"),
        "first_call_ms": round(first_call * 1000, 1),
        "single_embed_ms_avg": round(single_avg * 1000, 1),
        "batch8_total_ms": round(batch_total * 1000, 1),
        "batch_per_item_ms": round(batch_per_item * 1000, 1),
    }
    return meta, failures


def _clear_embedder_cache(embedder: Any) -> None:
    cache = getattr(embedder, "_cache", None)
    if isinstance(cache, dict):
        cache.clear()


# ---------------------------------------------------------------------------
# 阶段 4：离线加载（子进程，HF_HUB_OFFLINE=1）
# ---------------------------------------------------------------------------
def phase_offline(args: argparse.Namespace) -> Tuple[Dict[str, Any], List[str]]:
    _section(4, 5, "离线可复现（HF_HUB_OFFLINE=1 + 无效 HF_ENDPOINT 的子进程按 repo id 加载）")
    failures: List[str] = []

    if not args.model:
        failures.append("模型名未指定")
        return {"error": "no model"}, failures

    child_env = dict(os.environ)
    child_env["HF_HUB_OFFLINE"] = "1"
    child_env["TRANSFORMERS_OFFLINE"] = "1"
    # 故意指向无效端点：离线模式下不应有任何网络请求
    child_env["HF_ENDPOINT"] = "https://offline.invalid.example"
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONPATH"] = os.pathsep.join(
        [str(BACKEND_DIR), child_env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(SCRIPT_PATH),
        "--offline-child",
        "--milvus",
        "off",
        "--model",
        args.model,
    ]
    _info("子进程命令", " ".join(command))
    _info("子进程 HF_ENDPOINT", child_env["HF_ENDPOINT"])
    print("  子进程同样需要 import torch，可能耗时数分钟...", flush=True)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(BACKEND_DIR),
            env=child_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.offline_timeout,
        )
    except subprocess.TimeoutExpired:
        failures.append(f"离线子进程超时（{args.offline_timeout}s）")
        _fail("离线子进程超时", args.offline_timeout)
        return {"error": "timeout"}, failures
    elapsed = time.perf_counter() - started

    payload: Optional[Dict[str, Any]] = None
    for line in reversed((completed.stdout or "").splitlines()):
        if line.startswith("OFFLINE_CHILD_RESULT: "):
            try:
                payload = json.loads(line[len("OFFLINE_CHILD_RESULT: "):])
            except ValueError:
                payload = None
            break

    if completed.returncode != 0 or payload is None:
        _fail("离线加载失败", f"exit={completed.returncode}，{elapsed:.1f}s")
        tail = (completed.stderr or "").strip().splitlines()[-15:]
        for line in tail:
            print("    stderr| " + line)
        failures.append("离线加载失败（HF_HUB_OFFLINE=1 时无法按 repo id 加载）")
        return {"exit_code": completed.returncode, "stderr_tail": tail}, failures

    dim = payload.get("dimension")
    norm = payload.get("norm")
    _info("子进程总耗时", _fmt_secs(elapsed))
    _info("子进程判定", "离线加载成功（未访问网络）")
    _info("子进程维度", dim)
    _info("子进程向量 norm", round(norm, 6) if isinstance(norm, float) else norm)
    _info("子进程加载耗时", f"{payload.get('load_s')}s")
    if dim == 512:
        _ok("离线模式仍能按 repo id 加载，dimension=512")
    else:
        _fail("离线模式 dimension 异常", dim)
        failures.append(f"离线 dimension={dim}")
    if isinstance(norm, (int, float)) and abs(norm - 1.0) < 1e-3:
        _ok("离线模式向量已归一化")
    else:
        failures.append("离线向量未归一化")
        _fail("离线向量 norm 异常", norm)

    return {
        "ok": True,
        "child_elapsed_s": round(elapsed, 2),
        "child_load_s": payload.get("load_s"),
        "dimension": dim,
        "norm": norm,
        "hf_hub_offline": "1",
        "hf_endpoint_used": child_env["HF_ENDPOINT"],
        "cache_commit": payload.get("commit"),
    }, failures


def _offline_child_main(args: argparse.Namespace) -> int:
    """子进程入口：离线模式下真实加载并输出一行 JSON 证据。

    由 phase_offline() 通过 subprocess 调起。环境变量（HF_HUB_OFFLINE=1 与无效
    HF_ENDPOINT）由父进程注入，这里不回退/不修改，确保是真实离线验证。
    """
    configure_env(args)  # 已离线（子进程 env 已带 HF_HUB_OFFLINE=1）
    print(
        f"[offline-child] HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE')} "
        f"HF_ENDPOINT={os.environ.get('HF_ENDPOINT')} pid={os.getpid()}",
        flush=True,
    )
    started = time.perf_counter()
    from app.services.core.config import EmbeddingConfig
    from app.services.knowledge.embedding import BGEEmbedder

    embedder = BGEEmbedder(
        EmbeddingConfig(provider="local", model_name=args.model, device="cpu", normalize=True)
    )
    load_s = time.perf_counter() - started
    vec = embedder.embed("USB 设备超时无响应")
    snapshot, commit = _find_cached_snapshot(args.model)
    payload = {
        "dimension": embedder.dimension,
        "norm": _norm(vec),
        "load_s": round(load_s, 2),
        "commit": commit,
        "snapshot_dir": str(snapshot) if snapshot else None,
        "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
        "hf_endpoint": os.environ.get("HF_ENDPOINT"),
        "sentence_transformers": _safe_version("sentence_transformers"),
    }
    print("OFFLINE_CHILD_RESULT: " + json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


def _safe_version(package: str) -> Optional[str]:
    try:
        module = __import__(package)
        return getattr(module, "__version__", None)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# 阶段 5：Milvus 联合检索
# ---------------------------------------------------------------------------
MILVUS_DOC_ID = 9999
MILVUS_DOC_CONTENT = "USB 设备超时无响应的排查方法：检查线缆、驱动与供电"
MILVUS_QUERY = "USB 超时"


def phase_milvus(args: argparse.Namespace) -> Tuple[Dict[str, Any], List[str]]:
    _section(5, 5, "Milvus 联合真实检索（BGE 向量 → index → search → cleanup）")
    failures: List[str] = []

    from app.core.config import settings

    _info("settings.MILVUS_ENABLED", settings.MILVUS_ENABLED)
    _info("settings.MILVUS_HOST:PORT", f"{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
    _info("settings.EMBEDDING_PROVIDER", settings.EMBEDDING_PROVIDER)
    _info("settings.EMBEDDING_DIM / MILVUS_DIM", f"{settings.EMBEDDING_DIM} / {settings.MILVUS_DIM}")
    _info("settings.EMBEDDING_LOAD_TIMEOUT", settings.EMBEDDING_LOAD_TIMEOUT)

    try:
        from pymilvus import connections, utility
    except ImportError as exc:
        _fail("pymilvus 不可导入", exc)
        failures.append(f"pymilvus 不可导入: {exc}")
        return {"available": False, "error": str(exc)}, failures

    try:
        probe_alias = "bge_e2e_probe"
        connections.connect(
            alias=probe_alias,
            host=settings.MILVUS_HOST,
            port=str(settings.MILVUS_PORT),
            timeout=5,
        )
        server_version = utility.get_server_version(using=probe_alias)
        collections = utility.list_collections(using=probe_alias)
        connections.disconnect(probe_alias)
        _ok("Milvus 可连接", f"version={server_version}, collections={collections}")
    except Exception as exc:  # noqa: BLE001
        _fail("Milvus 不可连接", exc)
        failures.append(f"Milvus 不可连接: {exc}")
        return {"available": False, "error": str(exc)}, failures

    from app.services.knowledge.vector_service import VectorService

    # 冷加载可能超过默认类阈值 10s；e2e 场景下临时放宽
    VectorService._EMBEDDING_LOAD_TIMEOUT = float(os.environ.get("BGE_MILVUS_LOAD_TIMEOUT", "300"))
    started = time.perf_counter()
    service = VectorService()
    init_s = time.perf_counter() - started
    _info("VectorService 初始化耗时", _fmt_secs(init_s))
    _info("VectorService.available", service.available)
    _info("collection 名称 / 维度", f"{service.collection_name} / {service.dimension}")
    info = service.collection_info or {}
    _info("collection 实体数（操作前）", info.get("num_entities"))

    if not service.available:
        _fail("VectorService 不可用（Milvus 连接或 BGE 嵌入加载失败）")
        failures.append("VectorService.available=False")
        return {"available": False, "init_s": round(init_s, 2)}, failures

    meta: Dict[str, Any] = {
        "available": True,
        "server_version": server_version,
        "collection": service.collection_name,
        "dimension": service.dimension,
        "init_s": round(init_s, 2),
        "num_entities_before": info.get("num_entities"),
    }

    try:
        # --- index ---
        print(f"  index_document(doc_id={MILVUS_DOC_ID}) ...", flush=True)
        started = time.perf_counter()
        chunks = service.index_document(MILVUS_DOC_ID, content=MILVUS_DOC_CONTENT)
        index_s = time.perf_counter() - started
        _info("索引结果", f"chunks={chunks}, {_fmt_secs(index_s)}")
        meta["chunks_indexed"] = chunks
        meta["index_s"] = round(index_s, 2)
        if chunks > 0:
            _ok("index_document 成功")
        else:
            _fail("index_document 返回 0（未写入向量）")
            failures.append("index_document 返回 0")

        # --- search ---
        print(f"  search({MILVUS_QUERY!r}, top_k=3) ...", flush=True)
        started = time.perf_counter()
        hits = service.search(MILVUS_QUERY, top_k=3)
        search_s = time.perf_counter() - started
        meta["search_s"] = round(search_s, 2)
        meta["hits"] = hits
        if not hits:
            _fail("search 无命中")
            failures.append("Milvus search 无命中")
        else:
            print("  命中结果（BGE 语义检索）:")
            for rank, hit in enumerate(hits, 1):
                print(
                    f"    #{rank} doc_id={hit.get('id')} score={hit.get('score'):.4f} "
                    f"content={hit.get('content')!r}"
                )
            hit_ids = [hit.get("id") for hit in hits]
            if MILVUS_DOC_ID in hit_ids:
                rank = hit_ids.index(MILVUS_DOC_ID) + 1
                _ok(f"语义查询命中 doc_id={MILVUS_DOC_ID}", f"rank=#{rank}, score={hits[rank - 1]['score']:.4f}")
                meta["doc_rank"] = rank
            else:
                _fail(f"语义查询未命中 doc_id={MILVUS_DOC_ID}", f"hits={hit_ids}")
                failures.append(f"search 未命中 doc {MILVUS_DOC_ID}")
    finally:
        # --- cleanup ---
        try:
            cleaned = service.delete_document(MILVUS_DOC_ID)
            _info("清理 delete_document", cleaned)
            meta["deleted"] = cleaned
            if cleaned:
                remain = service._collection.query(  # noqa: SLF001 - e2e 验证需要确认清理结果
                    f"doc_id == {MILVUS_DOC_ID}", output_fields=["id"]
                )
                if remain:
                    _fail("清理后仍能查到该 doc", remain)
                    failures.append("清理不彻底")
                else:
                    _ok("已清理 doc 9999（query 确认为空）")
        except Exception as exc:  # noqa: BLE001 - 清理失败要报告但不掩盖主结果
            _fail("清理失败", exc)
            failures.append(f"清理失败: {exc}")

    info_after = service.collection_info or {}
    _info("collection 实体数（操作后）", info_after.get("num_entities"))
    meta["num_entities_after"] = info_after.get("num_entities")
    return meta, failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BGE 本地嵌入真实链路端到端验证（下载/加载/语义/离线/Milvus）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例（在 backend/ 目录下）:\n"
            "  ..\\.venv\\Scripts\\python.exe -X utf8 scripts\\verify\\bge_embedding_e2e.py\n"
            "  ..\\.venv\\Scripts\\python.exe -X utf8 scripts\\verify\\bge_embedding_e2e.py --skip-download --milvus off\n"
            "  $env:HF_HUB_OFFLINE='1'; ..\\.venv\\Scripts\\python.exe -X utf8 "
            "scripts\\verify\\bge_embedding_e2e.py --offline\n"
        ),
    )
    parser.add_argument("--model", default=MODEL_NAME, help=f"HF repo id（默认 {MODEL_NAME}）")
    parser.add_argument(
        "--endpoint",
        default=None,
        help=f"HF_ENDPOINT 覆盖（默认 {DEFAULT_HF_ENDPOINT}；传空字符串表示用官方源）",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="父进程离线模式：不访问网络，仅用本地缓存加载（等价 HF_HUB_OFFLINE=1）",
    )
    parser.add_argument("--offline-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-download", action="store_true", help="跳过下载，仅核验缓存")
    parser.add_argument("--skip-offline", action="store_true", help="跳过离线子进程验证")
    parser.add_argument("--skip-milvus", action="store_true", help="跳过 Milvus 联合检索")
    parser.add_argument(
        "--milvus",
        choices=["auto", "on", "off"],
        default="auto",
        help="Milvus 联合检索: auto=可连则做(默认), on=强制, off=跳过",
    )
    parser.add_argument(
        "--stages",
        default="all",
        help=f"只跑指定阶段，逗号分隔（{','.join(ALL_STAGES)}）或 all",
    )
    parser.add_argument("--offline-timeout", type=int, default=1800, help="离线子进程超时秒数（默认 1800）")
    parser.add_argument("--log-file", default=None, help="同时把完整输出写入该 UTF-8 文件")
    parser.add_argument("--json-out", default=None, help="把结构化证据 JSON 写入该文件")
    return parser.parse_args(argv)


def _selected_stages(args: argparse.Namespace) -> List[str]:
    if args.stages.strip().lower() in ("all", ""):
        return list(ALL_STAGES)
    selected = [item.strip().lower() for item in args.stages.split(",") if item.strip()]
    unknown = [item for item in selected if item not in ALL_STAGES]
    if unknown:
        raise SystemExit(f"--stages 含未知阶段: {unknown}；可选: {ALL_STAGES}")
    return selected


def _print_header(args: argparse.Namespace, env_info: Dict[str, Any]) -> None:
    print("=" * 78)
    print("BGE 本地嵌入真实链路端到端验证")
    print("=" * 78)
    print(f"  时间          : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Python        : {sys.version.split()[0]} ({sys.executable})")
    print(f"  工作目录      : {os.getcwd()}")
    print(f"  脚本          : {SCRIPT_PATH}")
    print(f"  模型          : {args.model}")
    print(f"  HF_ENDPOINT   : {env_info.get('HF_ENDPOINT') or '(未设置，将走官方源)'}")
    print(f"  HF_HUB_OFFLINE: {env_info.get('HF_HUB_OFFLINE') or '(未设置)'}")
    print(f"  HF 缓存目录   : {_hub_cache_dir()}")
    print(f"  Milvus 探测   : {env_info.get('milvus_probe')}（mode={args.milvus}）")
    print(flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    if args.offline_child:
        return _offline_child_main(args)

    log_handle = None
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8", buffering=1)
        sys.stdout = _Tee(sys.__stdout__, log_handle)
        sys.stderr = _Tee(sys.__stderr__, log_handle)
        print(f"日志同时写入: {log_path.resolve()}")

    total_started = time.perf_counter()
    results: Dict[str, Any] = {}
    failures: List[str] = []
    exit_code = 0

    try:
        env_info = configure_env(args)
        _print_header(args, env_info)
        selected = _selected_stages(args)

        snapshot: Optional[Path] = None
        commit: Optional[str] = None

        if STAGE_CACHE in selected:
            snapshot, commit, cache_meta, cache_failures = phase_cache(args)
            results["cache"] = cache_meta
            failures.extend(cache_failures)
            if snapshot is None:
                print("\n致命错误：模型缓存不可用，后续阶段无法执行。")
                exit_code = 2
                return exit_code
        else:
            snapshot, commit = _find_cached_snapshot(args.model)
            if snapshot is None:
                print("\n致命错误：模型未缓存，且本次跳过了下载阶段。")
                return 2

        embedder = None
        if STAGE_LOAD in selected:
            embedder, load_meta, load_failures = phase_load(args)
            results["load"] = load_meta
            failures.extend(load_failures)
        elif any(stage in selected for stage in (STAGE_SEMANTIC,)):
            embedder, load_meta, load_failures = phase_load(args)
            results["load"] = load_meta
            failures.extend(load_failures)

        if STAGE_SEMANTIC in selected:
            if embedder is None:
                embedder, load_meta, load_failures = phase_load(args)
                results["load"] = load_meta
                failures.extend(load_failures)
            semantic_meta, semantic_failures = phase_semantic(embedder)
            results["semantic"] = semantic_meta
            failures.extend(semantic_failures)

        if STAGE_OFFLINE in selected:
            if args.offline:
                _section(4, 5, "离线可复现（父进程已是离线模式）")
                _info("当前进程 HF_HUB_OFFLINE", os.environ.get("HF_HUB_OFFLINE"))
                _info("当前进程 HF_ENDPOINT", os.environ.get("HF_ENDPOINT") or "(未设置)")
                _ok("父进程已在离线模式完成加载与语义验证（见阶段 2/3）")
                results["offline"] = {
                    "mode": "parent-process",
                    "hf_hub_offline": os.environ.get("HF_HUB_OFFLINE"),
                    "ok": True,
                }
            elif args.skip_offline:
                _section(4, 5, "离线可复现（已按 --skip-offline 跳过）")
                results["offline"] = {"skipped": True}
            else:
                offline_meta, offline_failures = phase_offline(args)
                results["offline"] = offline_meta
                failures.extend(offline_failures)

        if STAGE_MILVUS in selected:
            if args.skip_milvus or args.milvus == "off":
                _section(5, 5, "Milvus 联合检索（已跳过）")
                results["milvus"] = {"skipped": True}
            elif not env_info.get("milvus_env_enabled") and args.milvus == "auto":
                _section(5, 5, "Milvus 联合检索（auto: 19530 不可连，跳过）")
                results["milvus"] = {"skipped": True, "reason": "milvus unreachable"}
            else:
                milvus_meta, milvus_failures = phase_milvus(args)
                results["milvus"] = milvus_meta
                failures.extend(milvus_failures)

        exit_code = 0 if not failures else 1
        return exit_code
    except BaseException as exc:  # noqa: BLE001 - 汇总所有异常为可读输出
        failures.append(f"未捕获异常: {exc}")
        print("\n致命异常：")
        traceback.print_exc()
        exit_code = 2
        return exit_code
    finally:
        total_elapsed = time.perf_counter() - total_started
        results["_meta"] = {
            "model": args.model,
            "total_elapsed_s": round(total_elapsed, 2),
            "failures": failures,
            "success": exit_code == 0,
            "stages": _safe_stages(args),
            "cache_commit": locals().get("commit"),
        }
        print()
        print("=" * 78)
        print("验证总结")
        print("=" * 78)
        for stage_name in ("cache", "load", "semantic", "offline", "milvus"):
            if stage_name not in results:
                continue
            payload = results[stage_name]
            print(f"  [{stage_name}]")
            for key, value in payload.items():
                rendered = _render_summary_value(key, value)
                if rendered:
                    print(f"    {key}: {rendered}")
        print(f"  总耗时: {_fmt_secs(total_elapsed)}")
        if failures:
            print(f"  结论: ❌ 失败 {len(failures)} 项")
            for item in failures:
                print(f"    - {item}")
        elif set(_safe_stages(args)) == set(ALL_STAGES):
            print("  结论: ✅ 全部检查通过（BGE 真实链路已打通）")
        else:
            print("  结论: ✅ 所有已执行阶段检查通过")
        print("=" * 78, flush=True)

        if args.json_out:
            try:
                out = Path(args.json_out)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                print(f"结构化证据已写入: {out.resolve()}")
            except OSError as exc:  # noqa: BLE001
                print(f"写入 --json-out 失败: {exc}")
        if log_handle is not None:
            try:
                sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
                log_handle.flush()
                log_handle.close()
            except Exception:  # noqa: BLE001
                pass


def _safe_stages(args: argparse.Namespace) -> List[str]:
    try:
        return _selected_stages(args)
    except SystemExit:
        return []


def _render_summary_value(key: str, value: Any) -> str:
    if key in ("files", "weights"):
        return ""
    if key in ("semantic_groups", "hits"):
        return ""
    if isinstance(value, float):
        return f"{value:.4f}" if abs(value) < 1e6 else str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)[:500]
    return str(value)


if __name__ == "__main__":
    sys.exit(main())
