# 部署指南

## 一键启动

```bash
cd deploy
docker compose up -d --build
```

启动后浏览器打开 **http://localhost** 即可使用。

## 服务列表

| 服务 | 端口 | 说明 |
|------|------|------|
| Frontend (Nginx) | 80 | Vue3 Web 应用 |
| Backend (FastAPI) | 8000 | REST API + 日志文件 (`logs/app.log`) |
| Worker | - | 异步任务处理器（当前为 keep-alive 占位，Celery 待接入；已禁用容器 healthcheck） |
| PostgreSQL | 5432 | 主数据库 |
| Redis | 6379 | 缓存 / Celery broker |
| Milvus (standalone) | 19530 / 9091 | 向量数据库（内嵌 etcd + local storage，v2.4.0） |
| MinIO | 9000 / 9001 | 对象存储（S3 API / Web Console） |
| Prometheus / Grafana | 9090 / 3000 | 监控采集 / 可视化 |

## 验证

```bash
curl http://localhost:8000/health                        # → {"status":"ok"}
curl http://localhost:8000/api/v1/vector/health          # → milvus_available=true；embedding_provider 为真实 provider
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9091/healthz   # Milvus → 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9000/minio/health/live  # MinIO → 200
```

浏览器访问 http://localhost

> 首次部署说明：`diagnostic-logs` / `knowledge-images` bucket 由后端启动时自动创建
> （`LogStorage` / `KnowledgeImageStorage`）；若运行用户无 `s3:CreateBucket` 权限，
> 需由管理员预先创建这两个 bucket。生产务必修改 MinIO 默认口令。

## 本地 BGE 嵌入（容器内）

后端镜像默认**不含** torch/sentence-transformers（`EMBEDDING_PROVIDER=auto` 在容器内会回退哈希嵌入）。
如需容器内真实 BGE 语义嵌入（BAAI/bge-small-zh-v1.5，512 维），使用覆盖文件叠加构建：

```bash
# 前置：宿主机已缓存模型（见 docs/20-Audit/verification/04-bge.md §5.3）
$env:HF_CACHE_DIR = "$env:USERPROFILE\.cache\huggingface"        # PowerShell
export HF_CACHE_DIR="$HOME/.cache/huggingface"                   # Linux/macOS

docker compose -f docker-compose.yml -f docker-compose.bge.yml config -q
docker compose -f docker-compose.yml -f docker-compose.bge.yml up -d --build backend worker

# 验收：应输出 BGEEmbedder 512（而非 HashingEmbedder）
docker compose -f docker-compose.yml -f docker-compose.bge.yml exec backend \
  python -c "from app.services.knowledge.embedding import get_embedder; e=get_embedder(); print(e.provider_name, e.dimension)"
```

覆盖文件会设置 `INSTALL_ML=true`（镜像 +2GB+）、`EMBEDDING_PROVIDER=local`、
`EMBEDDING_LOAD_TIMEOUT=120`、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`，并只读挂载 HF 缓存；
默认不叠加该文件时镜像保持精简。回滚：不叠加覆盖文件重新 `up -d --build backend worker`。

## 镜像版本与离线部署

- compose 中所有服务镜像均固定 tag（禁止 `:latest`）；升级时同步更新 tag 并重新验证。
- 生产/CI 建议进一步固定 digest：`docker inspect --format '{{index .RepoDigests 0}}' <image>`，
  将 `image:` 写成 `<repo>@sha256:...`。已验证示例：
  `minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`。
- Docker Hub 不可达时：配置 registry mirror（见「故障排查」），或在内网 registry 推送后改 image 地址，
  或 `docker save` / `docker load` 离线导入镜像（含 `deploy-backend`/`deploy-worker` 本地构建产物）。


## 故障排查

### Docker Hub 网络不通

配置镜像加速器：Docker Desktop → Settings → Docker Engine，添加：

```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
```

点击 Apply & Restart 后重试。

### 端口冲突

如果 80/8000 端口被占用：

```bash
# 修改 docker-compose.yml 中的端口映射
ports:
  - "8080:80"    # 改为 8080
```

### 清理重建

```bash
docker compose down -v     # 停止并删除所有数据
docker compose up -d --build
```

## 生产配置

### 环境变量

编辑 `docker-compose.yml` 中的 `backend.environment`：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `mock` | 改为 `deepseek` 启用 AI |
| `DEEPSEEK_API_KEY` | | 设置 DeepSeek API Key |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名称 |

### 扩展

```yaml
backend:
  deploy:
    replicas: 3
```

## 本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd apps/web
npm install
npm run dev
```
