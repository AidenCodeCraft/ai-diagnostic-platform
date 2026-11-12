#!/usr/bin/env python3
"""MinIO 对象存储真连端到端验证脚本（host 侧执行，可重复运行）。

覆盖链路：
  1. S3 SDK 直连（localhost:9000）：
     bucket 存在性检查/自动创建 → put_object → stat_object（size/etag）
     → get_object 逐字节比对 → presigned_get_object 实际 HTTP GET
     → remove_object → 再次 stat 应报 NoSuchKey。
  2. 后端真实代码类 LogStorage（save / materialize / delete）真连 MinIO。
  3. 后端真实代码类 KnowledgeImageStorage（save / get_bytes / presign_url / delete）真连 MinIO。
  4. 后端 HTTP API 端到端（需后端容器已启用 MinIO）：
     POST /api/v1/logs/upload → file_path 应为 minio://... → SDK 确认对象存在且大小/ETag 一致
     → POST /api/v1/logs/{id}/parse 成功（证明 materialize() 从 MinIO 下载可用）
     → DELETE /api/v1/logs/{id} → 对象消失。
     POST /api/v1/knowledge/images（multipart）→ knowledge-images bucket 真实写入
     → GET /api/v1/knowledge/images/{id} 字节一致 → 预签名 URL 可 GET。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe backend\\scripts\\verify\\minio_storage_e2e.py
    # 仅做 SDK/类直连、跳过 API 部分（后端未重启时）：
    .venv\\Scripts\\python.exe backend\\scripts\\verify\\minio_storage_e2e.py --skip-api

退出码：0 = 已执行的检查全部通过（API 不可达时按 SKIP 处理）；1 = 存在 FAIL；
        2 = MinIO 本身不可达/认证失败。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import os
import random
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 最小合法 1x1 PNG（透明像素），用于知识库图片链路验证
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

RESULTS: List[Dict[str, Any]] = []


# ----------------------------------------------------------------------
# 结果记录与断言
# ----------------------------------------------------------------------


class CheckFailure(AssertionError):
    """单条检查失败。"""


def record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append({"status": status, "name": name, "detail": detail})
    suffix = f" — {detail}" if detail else ""
    print(f"[{status:4s}] {name}{suffix}", flush=True)


def check(condition: bool, name: str, detail: str = "") -> None:
    if condition:
        record("PASS", name, detail)
    else:
        record("FAIL", name, detail)
        raise CheckFailure(f"{name}: {detail}")


def skip(name: str, detail: str = "") -> None:
    record("SKIP", name, detail)


def section(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MinIO 对象存储真连端到端验证")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("MINIO_VERIFY_ENDPOINT", os.getenv("MINIO_ENDPOINT", "localhost:9000")),
        help="MinIO S3 API 地址（host 侧，默认 localhost:9000）",
    )
    parser.add_argument("--access-key", default=os.getenv("MINIO_ACCESS_KEY", "minioadmin"))
    parser.add_argument("--secret-key", default=os.getenv("MINIO_SECRET_KEY", "minioadmin"))
    parser.add_argument("--secure", action="store_true", help="使用 HTTPS 连接 MinIO")
    parser.add_argument(
        "--api-base",
        default=os.getenv("API_BASE", "http://localhost:8000"),
        help="后端 API 根地址（默认 http://localhost:8000）",
    )
    parser.add_argument(
        "--log-bucket",
        default=os.getenv("MINIO_BUCKET", "diagnostic-logs"),
        help="日志 bucket（默认 diagnostic-logs）",
    )
    parser.add_argument(
        "--image-bucket",
        default=os.getenv("MINIO_KNOWLEDGE_BUCKET", "knowledge-images"),
        help="知识库图片 bucket（默认 knowledge-images）",
    )
    parser.add_argument("--skip-api", action="store_true", help="跳过 HTTP API 端到端部分")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="保留测试对象（默认全部清理；API 部分日志记录始终清理）",
    )
    return parser.parse_args()


# ----------------------------------------------------------------------
# 后端 settings 注入（让 app.* 类真连 host MinIO）
# ----------------------------------------------------------------------


def apply_backend_settings(args: argparse.Namespace) -> None:
    """在导入 app.* 之前把 settings 指向 host 侧 MinIO（localhost:9000）。"""
    os.environ["MINIO_ENABLED"] = "true"
    os.environ["MINIO_ENDPOINT"] = args.endpoint
    os.environ["MINIO_ACCESS_KEY"] = args.access_key
    os.environ["MINIO_SECRET_KEY"] = args.secret_key
    os.environ["MINIO_BUCKET"] = args.log_bucket
    os.environ["MINIO_KNOWLEDGE_BUCKET"] = args.image_bucket
    os.environ["MINIO_SECURE"] = "true" if args.secure else "false"

    import app.core.config as config_module

    s = config_module.settings
    s.MINIO_ENABLED = True
    s.MINIO_ENDPOINT = args.endpoint
    s.MINIO_ACCESS_KEY = args.access_key
    s.MINIO_SECRET_KEY = args.secret_key
    s.MINIO_BUCKET = args.log_bucket
    s.MINIO_KNOWLEDGE_BUCKET = args.image_bucket
    s.MINIO_SECURE = bool(args.secure)


# ----------------------------------------------------------------------
# 1. SDK 直连
# ----------------------------------------------------------------------


def sdk_connect(args: argparse.Namespace) -> Tuple[Any, Any]:
    from minio import Minio
    from minio.error import S3Error

    client = Minio(
        args.endpoint,
        access_key=args.access_key,
        secret_key=args.secret_key,
        secure=bool(args.secure),
    )
    try:
        buckets = client.list_buckets()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] 无法连接 MinIO {args.endpoint}: {exc}", flush=True)
        raise SystemExit(2) from exc
    print(f"connected endpoint={args.endpoint} buckets={[b.name for b in buckets]}")
    return client, S3Error


def ensure_bucket(client: Any, name: str) -> None:
    existed = client.bucket_exists(name)
    if not existed:
        client.make_bucket(name)
    check(True, f"bucket {name}", f"exists={existed}" + (" (created just now)" if not existed else ""))


def sdk_direct_roundtrip(client: Any, S3Error: Any, bucket: str, keep: bool) -> None:
    section("1. S3 SDK 直连：put/stat/get/presign/remove")

    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    key = f"verify/{run_id}-binary.bin"
    payload = b"MINIO-E2E-BINARY\x00" * 256 + uuid.uuid4().bytes  # 含 NUL 的确定字节
    payload_sha = sha256_hex(payload)
    payload_md5 = md5_hex(payload)
    print(f"object_key={key} bytes={len(payload)} sha256={payload_sha}")
    removed = False
    try:
        client.put_object(
            bucket,
            key,
            data=io.BytesIO(payload),
            length=len(payload),
            content_type="application/octet-stream",
            metadata={"x-amz-meta-source": "minio-storage-e2e"},
        )
        check(True, "put_object", f"bucket={bucket} key={key} size={len(payload)}")

        stat_info = client.stat_object(bucket, key)
        etag = (stat_info.etag or "").strip('"')
        check(stat_info.size == len(payload), "stat_object size", f"stat.size={stat_info.size} expected={len(payload)}")
        check(etag == payload_md5, "stat_object etag == md5(payload)", f"etag={etag} md5={payload_md5}")
        check(
            (stat_info.content_type or "") == "application/octet-stream",
            "stat_object content_type",
            str(stat_info.content_type),
        )

        resp = client.get_object(bucket, key)
        try:
            downloaded = resp.read()
        finally:
            resp.close()
            resp.release_conn()
        check(downloaded == payload, "get_object 逐字节一致", f"sha256={sha256_hex(downloaded)}")

        import httpx

        url = client.presigned_get_object(bucket, key, expires=timedelta(minutes=5))
        presp = httpx.get(url, timeout=10.0)
        check(presp.status_code == 200, "presigned_get_object HTTP 200", f"status={presp.status_code}")
        check(presp.content == payload, "presigned GET 内容逐字节一致", f"body_sha256={sha256_hex(presp.content)}")
        print(f"presigned_url={url.split('?')[0]}?... (query omitted)")

        client.remove_object(bucket, key)
        removed = True
        try:
            client.stat_object(bucket, key)
            record("FAIL", "remove_object 后对象消失", "stat_object 仍成功，对象未删除")
            raise CheckFailure("object still exists after remove_object")
        except S3Error as exc:
            check(True, "remove_object 后 stat 报 NoSuchKey", f"code={getattr(exc, 'code', None)}")
    finally:
        if not removed and not keep:
            try:
                client.remove_object(bucket, key)
            except Exception:  # noqa: BLE001
                pass


# ----------------------------------------------------------------------
# 2. 后端代码类 LogStorage host 直连
# ----------------------------------------------------------------------


def log_storage_roundtrip(args: argparse.Namespace, client: Any, S3Error: Any, keep: bool) -> None:
    section("2. 后端 LogStorage 类真连（save/materialize/delete）")
    from app.services.diagnostics.log_storage import LogStorage

    storage = LogStorage()
    check(storage.remote_available, "LogStorage.remote_available", f"enabled={storage.enabled} bucket={storage.bucket}")

    sample = (
        "2026-11-12 10:00:00.123  1234  5678 I AndroidRuntime: boot complete\n"
        "2026-11-12 10:00:01.456  1234  5678 E AndroidRuntime: java.lang.RuntimeException: boom\n"
        "2026-11-12 10:00:02.789  1234  5678 W System.err: call trace\n"
    ).encode("utf-8")
    import tempfile

    tmp_dir = Path(tempfile.mkdtemp(prefix="minio-e2e-log-"))
    local_file = tmp_dir / "minio_e2e_logstorage.log"
    local_file.write_bytes(sample)
    ref: Optional[str] = None
    try:
        ref = storage.save(local_file, "minio_e2e_logstorage.log")
        check(ref.startswith("minio://"), "LogStorage.save 返回 minio:// 引用", ref)
        bucket, _, key = ref[len("minio://"):].partition("/")
        check(bucket == args.log_bucket, "引用 bucket 正确", bucket)
        st = client.stat_object(bucket, key)
        check(st.size == len(sample), "MinIO 对象大小与本地一致", f"stat.size={st.size} local={len(sample)}")
        check((st.etag or "").strip('"') == md5_hex(sample), "MinIO ETag == md5(payload)", str(st.etag))

        materialized = storage.materialize(ref)
        materialized_bytes = Path(materialized).read_bytes()
        check(materialized_bytes == sample, "materialize 下载内容逐字节一致", str(materialized))

        storage.delete(ref)
        try:
            client.stat_object(bucket, key)
            record("FAIL", "LogStorage.delete 后对象消失", "stat_object 仍成功")
            raise CheckFailure("object still exists after LogStorage.delete")
        except S3Error as exc:
            check(True, "LogStorage.delete 后 stat 报 NoSuchKey", f"code={getattr(exc, 'code', None)}")
    finally:
        if ref and ref.startswith("minio://") and not keep:
            try:
                bucket, _, key = ref[len("minio://"):].partition("/")
                client.remove_object(bucket, key)
            except Exception:  # noqa: BLE001
                pass
        for p in [local_file, Path(tempfile.gettempdir()) / "diag_logs" / "minio_e2e_logstorage.log"]:
            try:
                p.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass


# ----------------------------------------------------------------------
# 3. 后端代码类 KnowledgeImageStorage host 直连
# ----------------------------------------------------------------------


def knowledge_image_storage_roundtrip(
    args: argparse.Namespace, client: Any, S3Error: Any, keep: bool
) -> None:
    section("3. 后端 KnowledgeImageStorage 类真连（save/get_bytes/presign_url/delete）")
    from app.services.knowledge.image_storage import KnowledgeImageStorage

    storage = KnowledgeImageStorage()
    check(storage.use_minio, "KnowledgeImageStorage.use_minio", f"bucket={storage.bucket}")
    check(storage.bucket == args.image_bucket, "知识库 bucket 名", storage.bucket)

    run_id = uuid.uuid4().hex
    data = PNG_1X1 + f"minio-e2e-{run_id}".encode()
    key = f"verify/{run_id}.png"
    import httpx

    try:
        returned = storage.save(key, data, "image/png")
        check(returned == key, "save 返回 storage_key", returned)
        st = client.stat_object(args.image_bucket, key)
        check(st.size == len(data), "MinIO 对象大小一致", f"stat.size={st.size} local={len(data)}")
        check((st.etag or "").strip('"') == md5_hex(data), "MinIO ETag == md5(payload)", str(st.etag))

        got = storage.get_bytes(key)
        check(got == data, "get_bytes 逐字节一致", f"sha256={sha256_hex(got)}")

        url = storage.presign_url(key, expires=300)
        check(bool(url and "X-Amz-Signature" in url), "presign_url 生成预签名 URL", (url or "")[:120])
        resp = httpx.get(url, timeout=10.0) if url else None
        check(resp is not None and resp.status_code == 200, "预签名 URL HTTP 200", f"status={getattr(resp, 'status_code', None)}")
        check(resp is not None and resp.content == data, "预签名 URL 内容一致", f"sha256={sha256_hex(resp.content) if resp else ''}")

        storage.delete(key)
        try:
            client.stat_object(args.image_bucket, key)
            record("FAIL", "delete 后对象消失", "stat_object 仍成功")
            raise CheckFailure("object still exists after KnowledgeImageStorage.delete")
        except S3Error as exc:
            check(True, "delete 后 stat 报 NoSuchKey", f"code={getattr(exc, 'code', None)}")
    finally:
        if not keep:
            try:
                client.remove_object(args.image_bucket, key)
            except Exception:  # noqa: BLE001
                pass


# ----------------------------------------------------------------------
# 4. 后端 HTTP API 端到端
# ----------------------------------------------------------------------

SAMPLE_LOG = (
    "2026-11-12 10:00:00.123  1234  5678 I ActivityManager: Start proc com.example.app\n"
    "2026-11-12 10:00:01.456  1234  5678 E AndroidRuntime: java.lang.RuntimeException: diagnostic demo\n"
    "2026-11-12 10:00:01.457  1234  5678 E AndroidRuntime: \tat com.example.MainActivity.onCreate(MainActivity.java:42)\n"
    "2026-11-12 10:00:02.789  1234  5678 W System.err: something odd happened\n"
    "2026-11-12 10:00:03.001  1234  5678 I System.out: recover ok\n"
    "2026-11-12 10:00:04.222  1234  5678 D NetworkMonitor: retry #2 success\n"
)


def _api_probe(api_base: str) -> bool:
    import httpx

    try:
        resp = httpx.get(f"{api_base.rstrip('/')}/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _s3_error_code(client: Any, S3Error: Any, bucket: str, key: str) -> str:
    try:
        client.stat_object(bucket, key)
        return "EXISTS"
    except S3Error as exc:
        return str(getattr(exc, "code", None) or exc)


def api_log_roundtrip(api_base: str, log_bucket: str, client: Any, S3Error: Any) -> bool:
    """执行日志上传/解析/删除 API 端到端；返回是否整体成功。"""
    import httpx

    section("4a. 日志 API 端到端（upload → parse → delete）")
    base = api_base.rstrip("/")
    sample_bytes = SAMPLE_LOG.encode("utf-8")
    expected_events = len([line for line in SAMPLE_LOG.splitlines() if line.strip()])
    created_id: Optional[int] = None
    try:
        resp = httpx.post(
            f"{base}/api/v1/logs/upload",
            files={"file": ("minio_e2e_sample.log", sample_bytes, "text/plain")},
            data={"device": "minio-e2e", "description": "MinIO E2E verification"},
            timeout=30.0,
        )
        check(
            resp.status_code == 200,
            "POST /logs/upload 返回 200",
            f"status={resp.status_code} body={resp.text[:300]}",
        )
        body = resp.json()
        created_id = body["id"]
        file_path = str(body.get("file_path") or "")
        print(f"log_id={created_id} file_path={file_path} size={body.get('size')} status={body.get('status')}")
        check(
            file_path.startswith(f"minio://{log_bucket}/logs/"),
            "响应 file_path 为 minio://<bucket>/logs/...",
            file_path,
        )

        bucket, _, key = file_path[len("minio://"):].partition("/")
        st = client.stat_object(bucket, key)
        check(st.size == len(sample_bytes), "MinIO 中对象存在且大小一致", f"size={st.size} local={len(sample_bytes)}")
        check(
            (st.etag or "").strip('"') == md5_hex(sample_bytes),
            "MinIO 对象 ETag == md5(上传文件)",
            str(st.etag),
        )

        resp = httpx.get(f"{base}/api/v1/logs/{created_id}", timeout=10.0)
        check(resp.status_code == 200, "GET /logs/{id} 返回 200", f"status={resp.status_code}")
        check(resp.json().get("file_path") == file_path, "GET /logs/{id} file_path 一致", str(resp.json().get("file_path")))

        resp = httpx.post(f"{base}/api/v1/logs/{created_id}/parse", timeout=60.0)
        check(
            resp.status_code == 200,
            "POST /logs/{id}/parse 返回 200（materialize 从 MinIO 下载成功）",
            f"status={resp.status_code} body={resp.text[:300]}",
        )
        parse_body = resp.json()
        print(
            f"parse: status={parse_body.get('status')} event_count={parse_body.get('event_count')} "
            f"error_count={parse_body.get('error_count')} source_type={parse_body.get('source_type')} "
            f"suggestions={len(parse_body.get('suggestions') or [])}"
        )
        check(parse_body.get("status") == "completed", "解析状态 completed", str(parse_body.get("status")))
        check(
            int(parse_body.get("event_count") or 0) == expected_events,
            "解析事件数与样例日志行数一致",
            f"event_count={parse_body.get('event_count')} expected={expected_events}",
        )

        resp = httpx.get(f"{base}/api/v1/logs/{created_id}/parse-status", timeout=10.0)
        check(
            resp.status_code == 200 and resp.json().get("status") == "parsed",
            "parse-status 为 parsed",
            f"status={resp.status_code} body={resp.text[:200]}",
        )

        resp = httpx.delete(f"{base}/api/v1/logs/{created_id}", timeout=10.0)
        check(resp.status_code == 204, "DELETE /logs/{id} 返回 204", f"status={resp.status_code} body={resp.text[:200]}")
        created_id = None
        code = _s3_error_code(client, S3Error, bucket, key)
        check(code == "NoSuchKey", "删除后 MinIO 对象消失（NoSuchKey）", f"stat code={code}")
        return True
    except CheckFailure as exc:
        record("FAIL", "日志 API 端到端未全部通过", str(exc))
        return False
    finally:
        if created_id is not None:
            try:
                httpx.delete(f"{base}/api/v1/logs/{created_id}", timeout=10.0)
            except Exception:  # noqa: BLE001
                pass


def api_image_roundtrip(
    api_base: str, image_bucket: str, client: Any, S3Error: Any, keep: bool
) -> bool:
    """执行知识库图片上传/读取 API + bucket/预签名验证；返回是否整体成功。"""
    import httpx

    section("4b. 知识库图片 API 端到端（upload → get → presign）")
    base = api_base.rstrip("/")
    run_id = uuid.uuid4().hex
    png_bytes = PNG_1X1 + f"minio-e2e-image-{run_id}".encode()
    sha = sha256_hex(png_bytes)
    expected_key = f"{sha[:2]}/{sha[2:4]}/{sha}.png"
    image_id: Optional[int] = None
    try:
        resp = httpx.post(
            f"{base}/api/v1/knowledge/images",
            files={"file": ("minio_e2e.png", png_bytes, "image/png")},
            timeout=30.0,
        )
        check(
            resp.status_code == 201,
            "POST /knowledge/images 返回 201",
            f"status={resp.status_code} body={resp.text[:300]}",
        )
        body = resp.json()
        image_id = body["id"]
        print(f"image_id={image_id} url={body.get('url')} mime={body.get('mime_type')} key={expected_key}")
        check(body.get("url") == f"/api/v1/knowledge/images/{image_id}", "响应 url 指向本平台图片端点", str(body.get("url")))

        st = client.stat_object(image_bucket, expected_key)
        check(st.size == len(png_bytes), "knowledge-images 对象存在且大小一致", f"size={st.size} local={len(png_bytes)}")
        check(
            (st.etag or "").strip('"') == md5_hex(png_bytes),
            "knowledge-images 对象 ETag == md5(payload)",
            str(st.etag),
        )

        resp = httpx.get(f"{base}/api/v1/knowledge/images/{image_id}", timeout=15.0)
        check(resp.status_code == 200, "GET /knowledge/images/{id} 返回 200（从 MinIO 读回）", f"status={resp.status_code}")
        check(resp.content == png_bytes, "API 返回图片字节与上传一致", f"sha256={sha256_hex(resp.content)}")
        check(
            (resp.headers.get("content-type") or "").startswith("image/png"),
            "API 返回 Content-Type=image/png",
            str(resp.headers.get("content-type")),
        )

        url = client.presigned_get_object(image_bucket, expected_key, expires=timedelta(minutes=5))
        presp = httpx.get(url, timeout=10.0)
        check(presp.status_code == 200, "knowledge-images 预签名 URL HTTP 200", f"status={presp.status_code}")
        check(presp.content == png_bytes, "预签名 URL 返回图片字节一致", f"sha256={sha256_hex(presp.content)}")

        # 后端类 presign_url 也使用同一 host endpoint（生产需注意对外 endpoint）
        from app.services.knowledge.image_storage import KnowledgeImageStorage

        class_url = KnowledgeImageStorage().presign_url(expected_key, expires=300)
        class_resp = httpx.get(class_url, timeout=10.0) if class_url else None
        check(
            class_resp is not None and class_resp.status_code == 200,
            "KnowledgeImageStorage.presign_url HTTP 200",
            f"status={getattr(class_resp, 'status_code', None)}",
        )
        return True
    except CheckFailure as exc:
        record("FAIL", "知识库图片 API 端到端未全部通过", str(exc))
        return False
    finally:
        # 无删除图片 API：清理对象，数据库记录（doc_id=None）作为验证残留保留
        if not keep:
            try:
                client.remove_object(image_bucket, expected_key)
            except Exception:  # noqa: BLE001
                pass
        if image_id is not None:
            print(
                f"[NOTE] image API 无删除端点，DB 中保留一条 KnowledgeImage 记录 id={image_id}（storage_key={expected_key}，对象已清理）",
                flush=True,
            )


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------


def main() -> int:
    args = parse_args()
    print("MinIO E2E verification")
    print(f"  endpoint      = {args.endpoint}")
    print(f"  api_base      = {args.api_base}")
    print(f"  log_bucket    = {args.log_bucket}")
    print(f"  image_bucket  = {args.image_bucket}")
    print(f"  skip_api      = {args.skip_api}")

    apply_backend_settings(args)
    client, S3Error = sdk_connect(args)

    section("0. bucket 存在性检查 / 自动创建")
    for bucket in (args.log_bucket, args.image_bucket):
        ensure_bucket(client, bucket)

    try:
        sdk_direct_roundtrip(client, S3Error, args.log_bucket, args.keep)
        log_storage_roundtrip(args, client, S3Error, args.keep)
        knowledge_image_storage_roundtrip(args, client, S3Error, args.keep)
    except CheckFailure as exc:
        record("FAIL", "SDK/类直连检查中断", str(exc))

    if args.skip_api:
        skip("HTTP API 端到端", "--skip-api")
    elif not _api_probe(args.api_base):
        skip("HTTP API 端到端", f"后端不可达: {args.api_base}/health")
    else:
        api_log_roundtrip(args.api_base, args.log_bucket, client, S3Error)
        api_image_roundtrip(args.api_base, args.image_bucket, client, S3Error, args.keep)

    # ── 汇总 ──
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    skipped = sum(1 for r in RESULTS if r["status"] == "SKIP")
    print("\n" + "=" * 72)
    print(f"SUMMARY: PASS={passed} FAIL={failed} SKIP={skipped} TOTAL={len(RESULTS)}")
    for r in RESULTS:
        if r["status"] != "PASS":
            print(f"  {r['status']}: {r['name']} — {r['detail']}")
    print("RESULT:", "PASS" if failed == 0 else "FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(2) from exc
