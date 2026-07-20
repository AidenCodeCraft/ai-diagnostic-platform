FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 使用清华 pip 镜像加速
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code + plugins
COPY backend/ .
COPY plugins/ /plugins/

# 删除 .env 防止覆盖 docker-compose 环境变量
RUN rm -f .env

# Create upload directory
RUN mkdir -p /app/data/raw

# Override alembic.ini sqlalchemy.url with environment variable, then start
CMD ["sh", "-c", "sed -i \"s|sqlalchemy.url = .*|sqlalchemy.url = ${DATABASE_URL}|\" alembic.ini && python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
