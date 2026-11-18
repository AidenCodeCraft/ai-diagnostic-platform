# CI 说明

## 工作流

| 工作流 | 触发 | 运行环境 | 是否需要外部服务 |
|---|---|---|---|
| `backend-tests.yml` | 每次 push / PR | GitHub 托管 `ubuntu-latest` | 否（内存 SQLite、mock LLM、Milvus 关闭） |
| `frontend-tests.yml` | 改动 `apps/web/**` | GitHub 托管 `ubuntu-latest` | 否 |
| `golden-regression.yml` | 手动 `workflow_dispatch` + 每日 02:00（北京时间） | **自托管 runner**，标签 `self-hosted`, `ai-diag` | 是：Milvus、BGE embedding 服务、MinIO、DeepSeek key |

## 为什么黄金集回归不能跑在托管 runner 上

`golden-regression` 需要：

- Milvus standalone 已加载 `knowledge_chunks_v2`（1024 维真实向量）；
- 自托管 BGE embedding 服务（CPU 推理，模型约 1.3GB）；
- MinIO 中的黄金集 `replay_snapshot`（历史日志切片）。

GitHub 托管 runner 无法预热这些状态，每次冷启需要下载模型 + 回填索引，耗时与费用都不可接受。

## 自托管 runner 待办（需要运维配合）

1. 在一台内网 Linux 机器上注册 runner，附加标签 `ai-diag`；
2. 在该机器上常驻 Milvus、BGE embedding 服务、MinIO（或能访问内网实例）；
3. 仓库 Variables 配置：`EMBEDDING_API_URL`、`MINIO_ENDPOINT`、`MILVUS_HOST`、`MILVUS_PORT`、`MILVUS_COLLECTION`；
4. 仓库 Secrets 配置：`DEEPSEEK_API_KEY`（仅 full 套件使用）。
5. runner 就绪后，把 `golden-regression.yml` 的触发条件加上 `push`，即可实现「每次提交跑回归」。

## 约定

- 快检（`fast`）只跑确定性断言（召回、命中、结论类别），不调用 LLM，无 API 成本；
- 全量（`full`）在夜间跑，含 LLM 判分；
- 回归红了只允许改代码或标记样本 `superseded`，**不允许下调阈值**（阈值变更需单独提交 + 管理员审批）。
