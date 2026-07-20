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
| Backend (FastAPI) | 8000 | REST API |
| PostgreSQL | 5432 | 主数据库 |
| Redis | 6379 | 缓存 |

## 验证

```bash
curl http://localhost:8000/health          # → {"status":"ok"}
curl http://localhost:8000/api/v1/test     # → {"message":"API working"}
```

浏览器访问 http://localhost

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
