# ═══════════════════════════════════════════════════════════
# AI Diagnostic Platform — Backend Dockerfile
# ═══════════════════════════════════════════════════════════
# 优化：多阶段构建 + .dockerignore + 精简依赖

FROM python:3.12-slim AS builder

WORKDIR /app

# 仅安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# pip 镜像加速
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 先复制依赖文件，利用 Docker 缓存层
COPY backend/requirements.txt .

# 安装依赖（生产不需要 dev 包）
RUN pip install --no-cache-dir -r requirements.txt

# ── 运行阶段 ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# 仅安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
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
