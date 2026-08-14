# ═══════════════════════════════════════════════════════════
# AI Diagnostic Platform — Backend Dockerfile
# ═══════════════════════════════════════════════════════════
# 优化：多阶段构建 + .dockerignore + 精简依赖
#
# 说明：
#   - 生产环境使用云端 Embedding（EMBEDDING_PROVIDER=deepseek），
#     因此不安装重型 ML 依赖（torch / sentence-transformers）。
#   - 如需本地 BGE 模型，请取消 builder 阶段末尾的
#     requirements-ml.txt 安装注释，并保持编译工具链（已包含）。

FROM python:3.12-slim AS builder

WORKDIR /app

# 安装编译依赖（grpcio、psycopg2 等可能需要本地编译）
# gcc / g++ / make / libpq-dev 保证无预编译 wheel 的包也能构建成功
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# pip 镜像加速
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 先复制依赖文件，利用 Docker 缓存层
# 注意：构建上下文是仓库根目录（docker-compose context: ..）
COPY backend/requirements.txt ./requirements.txt

# 安装基础依赖（生产环境不需要本地 ML 依赖）
# --default-timeout 提升大包下载的容错性
# --no-build-isolation 可避免部分包因构建隔离缺少工具链而失败（视需要开启）
RUN pip install --no-cache-dir --default-timeout=300 -r requirements.txt

# （可选）本地 ML 依赖 — 仅当需要本地 BGE 嵌入/重排序时取消注释
# RUN pip install --no-cache-dir --default-timeout=600 -r requirements-ml.txt
# COPY backend/requirements-ml.txt ./requirements-ml.txt

# ── 运行阶段 ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# 仅安装运行时依赖（psycopg2-binary 等已含动态库，无需编译工具链）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 site-packages
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用代码（.dockerignore 排除 tests/、__pycache__/ 等）
COPY backend/ .
COPY plugins/ /plugins/

# 清理
RUN rm -f .env .env.* && mkdir -p /app/data/raw

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["sh", "-c", "python -c \"from app.database.session import init_db; init_db(); print('DB tables created')\" && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
