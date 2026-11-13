# BGE 本地嵌入真实链路验证

- **日期**：2026-11-12
- **执行**：Agent Team 成员 `bge-embedding`
- **关联任务**：`task-4`（BGE 本地模型真实下载与语义嵌入验证）→ `task-9`（Docker 内本地 BGE 部署：compose 覆盖文件 + 文档）
- **状态**：✅ 本地 venv 全链路 **PASS**（真实下载 / 真实加载 / 语义质量 / 离线加载 / Milvus 联合检索）；新增集成测试默认 skip（默认 7 skipped）；门槛测试 **7 passed**；全量 pytest **473 passed / 18 skipped / 0 failed**（基线 466 passed / 1 skipped，无回归）；**Docker 内本地 BGE 部署方案已落地**：`deploy/docker-compose.bge.yml` 覆盖文件 `docker compose config` 验证通过（INSTALL_ML=true / EMBEDDING_PROVIDER=local / 只读缓存挂载），见 §5.3

## 1. 背景与结论

缺口背景：环境已安装 `sentence-transformers 5.7.0 / torch 2.13.0 / transformers 5.15.0`，
但 **huggingface.co 被墙**，此前只验证过「超时回退 hash 嵌入」；BGE 本地模型
（`BAAI/bge-small-zh-v1.5`，512 维）**从未真实下载、加载、推理过**，语义质量与
离线可部署性均无证据。默认测试 `tests/conftest.py` 又强制
`EMBEDDING_PROVIDER=hash`，天然覆盖不到真实 BGE 分支。

本次完成：

| # | 验证项 | 结论 |
|---|--------|------|
| 1 | hf-mirror 真实下载 `BAAI/bge-small-zh-v1.5` | ✅ commit `7999e1d3…`；13 文件；权重大盘 91.4 MiB；下载 ≈8–10 min（慢速镜像 ~200 KB/s），落盘 `C:\Users\EDY\.cache\huggingface\hub` |
| 2 | 真实加载（`BGEEmbedder` 按 repo id，CPU） | ✅ `dimension=512`、`health_check=True`；冷加载 15.35s / 同进程二次加载 12.28s |
| 3 | 中文语义质量（4 组故障语义样本对） | ✅ 排序 4/4 正确；USB 组 `cos(相近)=0.7881` vs `cos(无关)=0.5461`（Δ+0.2419） |
| 4 | 归一化 & batch/单条一致性 | ✅ `||v||≈1.0`（最大偏差 7.5e-8）；batch vs 单条 `max|diff|=1.04e-7` |
| 5 | CPU 推理性能 | ✅ batch 8 条 69.7ms（8.7 ms/条）；单条 137.9 ms/条（n=3，Python 调度开销大） |
| 6 | 离线可复现（`HF_HUB_OFFLINE=1`） | ✅ 新进程 + 无效 `HF_ENDPOINT` 仍按 repo id 加载成功，dim=512、norm=1.0，136.5s |
| 7 | Milvus 联合真实检索 | ✅ Milvus v2.4.0：`index_document(9999)` → `search("USB 超时")` **rank#1 doc_id=9999 score=0.7332** → 清理删除确认 |
| 8 | 新增集成测试默认 skip | ✅ `RUN_REAL_BGE=1` 门槛；默认全量 pytest 收集 491 tests 无错误、不执行真实模型 |
| 9 | 可复现脚本 | ✅ `backend/scripts/verify/bge_embedding_e2e.py` 五阶段一键跑通（总 362.4s，exit=0） |
| 10 | Docker 内本地 BGE 部署方案（task-9） | ✅ 新增 `deploy/docker-compose.bge.yml` 覆盖文件；`docker compose config -q` 通过，INSTALL_ML=true / EMBEDDING_PROVIDER=local / HF_HUB_OFFLINE=1 / 只读缓存挂载全部断言通过（见 §5.3、附录 C） |

> **关键发现（详见 §9）**：
> 1. **缓存命中 ≠ 不联网**：transformers 对 repo id 会做 `find_adapter_config_file()` 等
>    元数据探测，huggingface.co 不可达时会**长时间挂起**（实测 pytest 卡住 7+ 分钟）。
>    离线/内网部署必须设 `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1`
>    （或可达的 `HF_ENDPOINT`）。Docker 覆盖文件已内置这两个变量。
> 2. `VectorService` 原先硬编码 10s 加载超时且超时后永久降级关键词（冷加载 15.35s 会触发）——
>    **已由 Lead 并行修复**：改为读取 `settings.EMBEDDING_LOAD_TIMEOUT`、共享后台加载线程、
>    超时可重试/回填（§9.2 #1）。
> 3. **Docker 后端镜像默认不含 torch / sentence-transformers**，容器内
>    `EMBEDDING_PROVIDER=local` 会静默回退 hash 嵌入；真实 BGE 用 §5.3 的
>    `deploy/docker-compose.bge.yml` 一键启用（INSTALL_ML=true 构建 + 只读挂载缓存）。
> 4. Windows 上 torch import 极慢（首次 7–8 分钟，多为 Defender 扫描 DLL）；属环境因素，
>    部署到容器不受此影响，但本地开发/测试要预留时间。

## 2. 依赖与安装

### 2.1 实测版本（venv：`G:\ai-diagnostic-platform\.venv`，Python 3.12.13）

| 包 | 版本 | 说明 |
|----|------|------|
| sentence-transformers | 5.7.0 | BGE 加载/推理（`requirements-ml.txt`：`sentence-transformers>=3.0.0`） |
| torch | 2.13.0+cpu | CPU 版；无需 CUDA |
| transformers | 5.15.0 | ST 5.7 依赖 |
| huggingface_hub | 1.27.0 | 模型下载/缓存 |
| numpy | 2.5.2 | 向量计算 |
| pymilvus | 2.5.4 | Milvus 客户端（需 `setuptools 80.9.0` 提供 `pkg_resources`，`>=81` 已移除） |

### 2.2 安装命令

```powershell
# 在 backend/ 目录下（本地 BGE / 重排器能力；约 +2GB 依赖）
& ..\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt `
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 如需显式指定 CPU 版 torch（避免拉取 CUDA 巨包）：
& ..\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
```

`backend/requirements-ml.txt` 当前内容（可选依赖，默认不随生产镜像安装）：

```text
# 可选：本地 ML 能力（本地嵌入 + 本地重排序）
# 生产环境若使用云端 Embedding API（EMBEDDING_PROVIDER=deepseek/openai），
# 无需安装本文件，可显著减小镜像体积、加快构建。
# 本地开发/离线场景启用本地 BGE 模型时安装：
#   pip install -r requirements-ml.txt
# 注意：本文件依赖 torch（约 2GB+），需在含编译工具链的环境安装。
sentence-transformers>=3.0.0    # BGE Embedding + BGE-Reranker
```

### 2.3 安装注意事项

- venv 若无 `setuptools`，`pymilvus 2.5.4` 会因 `pkg_resources` 缺失而不可导入；
  本项目 `requirements.txt` 已固定 `setuptools==80.9.0`，按 requirements 安装即可。
- Windows 下首次 `import torch` 可能耗时 **7–8 分钟**（Defender 实时扫描 torch DLL），
  第二次起约 **2–3 分钟**；这是本机环境现象，不是代码问题。

## 3. 模型真实下载（hf-mirror）

### 3.1 网络事实（实测）

- `huggingface.co`：TCP/HTTPS 超时，不可用；
- `hf-mirror.com`：正常，可下载模型文件（但速度较慢，约 200 KB/s）。

### 3.2 下载命令

**关键：`HF_ENDPOINT` 必须在 import `huggingface_hub` / `sentence_transformers` 之前设置**
（huggingface_hub 在 import 时把端点固化为常量，运行中改 `os.environ` 不生效）。

```powershell
# PowerShell（Windows）：设置镜像端点后真实下载到默认缓存
$env:HF_ENDPOINT = 'https://hf-mirror.com'
& G:\ai-diagnostic-platform\.venv\Scripts\python.exe -c @"
from huggingface_hub import snapshot_download
print(snapshot_download('BAAI/bge-small-zh-v1.5'))
"@
# 输出（节选）：
# C:\Users\EDY\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5\snapshots\7999e1d3359715c523056ef9478215996d62a620
```

### 3.3 下载结果（实测）

| 项目 | 值 |
|------|-----|
| repo | `BAAI/bge-small-zh-v1.5` |
| commit | `7999e1d3359715c523056ef9478215996d62a620`（本地 `refs/main` 与远端 `model_info().sha` 一致） |
| 缓存根目录 | `C:\Users\EDY\.cache\huggingface\hub` |
| repo 缓存目录 | `C:\Users\EDY\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5` |
| snapshot 目录 | `…\snapshots\7999e1d3359715c523056ef9478215996d62a620` |
| 文件数 / snapshot 体积 | 13 个 / **183.34 MiB**（含 safetensors + bin 双份权重） |
| repo 目录磁盘占用 | **274.73 MiB**（snapshot 副本 183.34 + HF blobs 91.39） |
| 权重 | `model.safetensors` 95,827,648 B；`pytorch_model.bin` 95,842,633 B |
| SHA256 | safetensors `354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026`；bin `7c5fe667bbed05dc10e246e229b701ad266fe4d95ab946e9e5aa402056611b88` |
| config | `BertModel`，`hidden_size=512`，`max_position_embeddings=512`，`vocab_size=21128`，4 层 / 8 头 |
| 下载耗时 | 首次真实下载 **≈481–618s**（两个并行 job 经 HF 缓存锁串行化后落地；hf-mirror 约 200 KB/s）；二次运行 `snapshot_download` 仅 **1.56s**（纯缓存校验） |

文件清单（snapshot，按体积排序）：

```text
95,842,633  91.40 MiB  pytorch_model.bin
95,827,648  91.39 MiB  model.safetensors
   439,125   0.42 MiB  tokenizer.json
   109,540   0.10 MiB  vocab.txt
    27,670   0.03 MiB  README.md
     1,519   0.00 MiB  .gitattributes
       776   0.00 MiB  config.json
       367   0.00 MiB  tokenizer_config.json
       349   0.00 MiB  modules.json
       190   0.00 MiB  1_Pooling\config.json
       125   0.00 MiB  special_tokens_map.json
       124   0.00 MiB  config_sentence_transformers.json
        52   0.00 MiB  sentence_bert_config.json
```

### 3.4 缓存目录结构（HuggingFace hub 布局）

```text
C:\Users\EDY\.cache\huggingface\hub\
└── models--BAAI--bge-small-zh-v1.5\
    ├── blobs\                        # 内容寻址存储（91.39 MiB）
    ├── refs\main                     # 指向当前 commit（7999e1d3…）
    ├── snapshots\7999e1d3…\          # 按 commit 组织的可见文件树（183.34 MiB）
    └── trees\                        # 远端文件树缓存（少量元数据）
```

> Windows 非管理员会话下 huggingface_hub 无法创建符号链接，会改为**复制**文件，
> 因此 repo 目录实际磁盘占用约为「模型文件体积 + blobs」≈ 275 MiB（Linux 容器内
> 为硬链接，占用约一半）。

## 4. 真实加载与语义质量

### 4.1 加载方式

代码路径：`backend/app/services/knowledge/embedding.py` 的 `BGEEmbedder`
→ `SentenceTransformer(config.model_name, device="cpu")`，按 **repo id** 加载（离线时同样）。
`normalize=True` + `dimension=512`，与 `EMBEDDING_DIM` / `MILVUS_DIM` 对齐。

### 4.2 加载耗时（CPU，权重已缓存）

| 指标 | 数值 | 说明 |
|------|------|------|
| `import sentence_transformers`（含 torch） | **138.8s**（2.31min） | 本次 e2e 进程首次；系统级**首次**曾 7–8min（Defender 扫描），文件预热后同一机器可降至约 20–30s |
| 冷加载（首次实例化模型） | **15.35s** | 权重已缓存，含 tokenizer/BERT 初始化 |
| 热加载（同进程第二次实例化） | **12.28s** | 权重在 OS 页缓存中；生产应只加载一次 |

> 耗时说明：Windows + Defender 实时扫描使 `import torch` 在本机首次极慢；后续
> 缓存预热后实测 pytest 全套 7 用例（主进程 + 离线子进程共两次 import）仅 **52.06s**。
> 该现象属本机环境，容器/Linux 不受影响。

`dimension=512` ✅、`health_check()=True` ✅、torch CPU 线程数 12。

### 4.3 中文语义相似度（真实证据）

每组：查询句 vs 语义相近句 / vs 语义无关句（归一化向量余弦）。

| 组 | 查询句 | 相近句 | cos(相近) | 无关句 | cos(无关) | 差值 Δ |
|----|--------|--------|-----------|--------|-----------|--------|
| USB 超时 | USB 设备超时无响应 | USB 接口通信超时 | **0.7881** | 磁盘空间不足导致服务崩溃 | 0.5461 | **+0.2419** |
| 内核 panic | 内核 panic 导致系统重启 | Kernel panic 触发系统崩溃重启 | **0.8108** | 数据库连接池耗尽导致请求失败 | 0.5195 | **+0.2913** |
| 网络丢包 | 网络丢包严重导致通信中断 | 网卡丢包引起数据传输中断 | **0.8713** | 内存 OOM 导致服务进程被杀死 | 0.5433 | **+0.3280** |
| 内存 OOM | 内存 OOM 导致服务进程被杀死 | 内存溢出 OutOfMemory 进程崩溃 | **0.7219** | USB 设备超时无响应 | 0.4418 | **+0.2802** |

结论：4/4 组排序正确且区分度均 > 0.24，BGE 中文语义能力真实可用（不是哈希词形匹配）。
（说明：与生产代码一致，未加 BGE 检索指令前缀 `为这个句子生成表示以用于检索相关文章：`；
若用于「短查询 → 长文档」检索，可在 query 侧加前缀进一步提升。）

### 4.4 归一化与 batch/单条一致性

| 检查 | 结果 |
|------|------|
| 向量 L2 norm | `[1.0, 1.0, 1.0, 1.0]`，最大偏差 **7.5e-8** ✅ |
| batch embed vs 逐条 embed | `max|diff| = 1.04e-7`（float32 误差内）✅ |

### 4.5 CPU 推理性能（清空缓存后实测）

| 场景 | 数值 |
|------|------|
| 首次调用（含 warmup） | 326.3 ms |
| 单条 `embed()` 平均（n=3） | **137.9 ms/条** |
| `embed_batch()` 8 条 | 69.7 ms 总计 → **8.7 ms/条** |
| Milvus `search`（top_k=3，1 chunk） | 50 ms（含查询嵌入） |

说明：单条耗时偏高是因为每次调用都触发 torch 线程调度/同步开销（12 线程 CPU）；
**批量嵌入 8.7 ms/条** 更接近生产吞吐（`document_indexer` 走 batch）。CPU 上
512 维小模型完全可接受，无需 GPU。

## 5. 离线可复现与部署方案

### 5.1 离线验证证据（子进程，真实）

父进程以子进程方式运行同一脚本（`--offline-child`），注入：

```text
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_ENDPOINT=https://offline.invalid.example   # 故意无效：任何联网尝试都会失败
```

结果 ✅：

```text
[INFO] 子进程总耗时 → 136.5s (2.27min)      # 含 torch/ST import（~134s）+ 模型加载
[INFO] 子进程判定 → 离线加载成功（未访问网络）
[INFO] 子进程维度 → 512
[INFO] 子进程向量 norm → 1.0
[PASS] 离线模式仍能按 repo id 加载，dimension=512
[PASS] 离线模式向量已归一化
```

即：**模型已完整落盘，可在完全断网/无外网的部署环境按 repo id 加载使用**。

### 5.2 「缓存命中」不等于「不联网」——必须显式离线

实测坑：在 `RUN_REAL_BGE=1` 的 pytest 进程里（未设置离线变量/镜像端点），
`SentenceTransformer(repo_id)` 即使命中本地缓存，transformers 仍会调用
`find_adapter_config_file()` → `cached_file()` → **HTTP 探测 huggingface.co**，
在被墙环境下 `socket.create_connection` 长时间挂起（实测 CPU 停在 5s、7+ 分钟无进展）。

因此离线/内网运行必须三选一：

```powershell
# 方案 A（推荐，最稳）：强制离线，只读本地缓存
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'

# 方案 B：设置可达的镜像端点（会做少量元数据请求）
$env:HF_ENDPOINT = 'https://hf-mirror.com'

# 方案 C：同时设置（推荐用于 Docker：既离线又保留端点兜底）
$env:HF_ENDPOINT = 'https://hf-mirror.com'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
```

本仓库新增测试 `test_bge_real.py` 在 `RUN_REAL_BGE=1` 时已自动 `setdefault`
上述离线变量，避免该挂起（见 §7）。`bge_embedding_e2e.py --offline` 同理。

### 5.3 Docker 部署方案（用 compose 覆盖文件启用镜像内真实 BGE）

**现状**：`backend/Dockerfile` 默认只安装 `requirements.txt`，明确注释
「生产环境使用云端 Embedding，因此不安装重型 ML 依赖（torch / sentence-transformers）」。
即 **backend 容器内 `EMBEDDING_PROVIDER=local/auto` 会静默回退到 hash 嵌入**
（`_sentence_transformers_available=False`），语义检索质量不达标。

为容器内运行真实 BGE，本次新增 **`deploy/docker-compose.bge.yml`**（compose override，
叠加在基础 compose 之上，**不修改** `deploy/docker-compose.yml` / `backend/Dockerfile`）。
其依赖的基础接口（已落地）：

- `backend/Dockerfile`：新增 `ARG INSTALL_ML=false`；`INSTALL_ML=true` 时在 builder 阶段
  `pip install --no-cache-dir --default-timeout=600 -r requirements-ml.txt`
  （torch + sentence-transformers），随后与基础依赖一起复制到运行阶段；
- `deploy/docker-compose.yml`：backend / worker 的 `build.args.INSTALL_ML: "${INSTALL_ML:-false}"`；
  backend 环境变量透传 `EMBEDDING_LOAD_TIMEOUT: "${EMBEDDING_LOAD_TIMEOUT:-30}"`、
  `HF_ENDPOINT: "${HF_ENDPOINT:-}"`、`HF_HUB_OFFLINE: "${HF_HUB_OFFLINE:-0}"`、
  `TRANSFORMERS_OFFLINE: "${TRANSFORMERS_OFFLINE:-0}"`。

#### 一键启用步骤（在仓库根目录执行）

```powershell
# 0) 前置：宿主机已有 BGE 模型缓存（见 §3；默认路径 %USERPROFILE%\.cache\huggingface）
#    必须指向「缓存根目录」（其下含 models--BAAI--bge-small-zh-v1.5）
$env:HF_CACHE_DIR = "$env:USERPROFILE\.cache\huggingface"

# 1) 校验合并后的配置（不构建、不启动；未设置 HF_CACHE_DIR 会直接报错）
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.bge.yml config -q

# 2) 重建并启动 backend / worker
#    ⚠ 首次构建需在镜像内安装 torch + sentence-transformers：镜像 +2GB 以上，
#      构建耗时数分钟～十几分钟（取决于网络/镜像源）；构建产物可复用
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.bge.yml up -d --build backend worker

# 3) 预热（强烈建议，接流量前执行一次，避免首个请求等待模型加载）
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.bge.yml exec backend `
  python -c "from app.services.knowledge.embedding import get_embedder; e=get_embedder(); print(e.provider_name, e.dimension)"
# 期望输出: BGEEmbedder 512
```

Linux / macOS：`export HF_CACHE_DIR="$HOME/.cache/huggingface"`，其余命令相同。

#### 覆盖文件带来的配置差异（实测 `docker compose config` 断言）

| 配置项 | 默认 compose（不叠加） | 叠加 `docker-compose.bge.yml` 后 |
|---|---|---|
| backend / worker `build.args.INSTALL_ML` | `false` | **`true`**（镜像内含 torch + sentence-transformers） |
| `EMBEDDING_PROVIDER` | `${EMBEDDING_PROVIDER:-auto}` | **`local`**（强制真实本地 BGE，杜绝 api/auto 分支） |
| `EMBEDDING_LOAD_TIMEOUT` | `"${EMBEDDING_LOAD_TIMEOUT:-30}"` | **`"${EMBEDDING_LOAD_TIMEOUT:-120}"`** |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | `"0"` / `"0"` | **`"1"` / `"1"`**（完全离线，不访问 huggingface.co） |
| `HF_HOME` | 默认 | `/root/.cache/huggingface` |
| HF 缓存挂载 | 无 | **`${HF_CACHE_DIR}:/root/.cache/huggingface:ro`**（只读 bind 长语法，兼容 Windows 盘符路径） |
| `HF_ENDPOINT` | 透传 | `${HF_ENDPOINT:-https://hf-mirror.com}`（仅后备，离线模式下不会使用） |

说明：
- **`EMBEDDING_LOAD_TIMEOUT=120`**：默认 30s 对 CPU 冷加载（实测 15.35s + 容器冷启动抖动）
  偏紧，超时会静默回退 hash；`VectorService` 已改为读取该配置（§9.2 #1），因此这里调大即生效。
- **只读挂载**：模型不进镜像（体积/更新问题），运行时只读宿主缓存；容器内不写缓存，
  配合 `HF_HUB_OFFLINE=1` 不会触发任何下载。
- 可选：在 override 中取消注释 `EMBEDDING_HASH_FALLBACK: "false"`，让本地 BGE 加载失败时
  硬失败而不是静默回退 hash（便于验收，但会放大瞬时故障）。

#### 验证与验收判定

不构建镜像即可先校验合并配置（本次实测结果见附录 C）：

```powershell
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.bge.yml config --format json
# 断言：build.args.INSTALL_ML == "true"
#       environment.EMBEDDING_PROVIDER == "local"
#       environment.EMBEDDING_LOAD_TIMEOUT == "120"
#       environment.HF_HUB_OFFLINE == "1" / TRANSFORMERS_OFFLINE == "1"
#       volumes 含 bind: <HF_CACHE_DIR> -> /root/.cache/huggingface, read_only: true

# 对照默认配置（不叠加 override）
docker compose -f deploy/docker-compose.yml config --format json
# 断言：build.args.INSTALL_ML == "false"；volumes 无 /root/.cache/huggingface 挂载
```

容器启动后的运行期验收：

| # | 检查 | 期望 |
|---|------|------|
| 1 | `curl -s http://localhost:8000/api/v1/vector/health` | `embedding_provider` 为 `BGEEmbedder`（不是 `HashingEmbedder`） |
| 2 | `curl -s -X POST http://localhost:8000/api/v1/vector/embed -H "Content-Type: application/json" -d '{"text":"USB 设备超时无响应"}'` | `dimension=512`，embedding 非全零 |
| 3 | `docker compose ... logs backend \| grep -E "Using local BGE\|BGEEmbedder"` | 出现 `[Embedding] Using local BGE embedder (dim=512)` |
| 4 | 若日志出现「使用哈希嵌入兜底」 | **未生效**：检查镜像是否装 ST、缓存挂载路径、HF_HUB_OFFLINE 配置 |

> `/api/v1/vector/health` 的 `embedding_provider` 已由 Lead 并行改为返回真实 provider
> （`get_embedder().provider_name`），因此该字段可直接作为验收判定（§9.2 #2）。

#### 不需要本地 BGE 时（回滚/保持精简镜像）

不要叠加本覆盖文件即可（基础 compose 默认 `INSTALL_ML=false`，镜像不含 torch，
`EMBEDDING_PROVIDER` 默认 `auto`——容器内会回退 hash；生产建议改配云端
`EMBEDDING_PROVIDER=api` + `EMBEDDING_API_URL/KEY`，无需 torch、镜像精简，这是
Dockerfile 默认设计的意图）。

## 6. Milvus 联合真实检索（可选，已验证）

前置：Milvus v2.4.0（standalone + 内嵌 etcd + local storage）已由队友启动，
`localhost:19530` 可连；`pymilvus 2.5.4`；collection `knowledge_docs`（dim=512）。

验证脚本阶段 5（venv 进程直连，未用 HTTP API）：

```text
settings.MILVUS_ENABLED=True, EMBEDDING_PROVIDER=local, EMBEDDING_DIM=512, MILVUS_DIM=512
[PASS] Milvus 可连接 → version=v2.4.0, collections=['knowledge_docs']
[INFO] VectorService 初始化耗时 → 16.48s
[INFO] collection 名称 / 维度 → knowledge_docs / 512
index_document(doc_id=9999, content="USB 设备超时无响应的排查方法：检查线缆、驱动与供电")
  → chunks=1, 3.84s
search('USB 超时', top_k=3)
  → #1 doc_id=9999 score=0.7332 content='USB 设备超时无响应的排查方法：检查线缆、驱动与供电'
[PASS] 语义查询命中 doc_id=9999 → rank=#1, score=0.7332
cleanup: delete_document(9999) → True，query doc_id==9999 结果为空 ✅
```

说明：
- 全程未 drop collection、未清空 `knowledge_docs`（后端容器共用该 collection），
  仅插入并删除了临时 doc `9999`；
- `num_entities` 删除后不会立即下降（Milvus 统计延迟口径：操作前 3 → 操作后 4），
  以 `query` 确认为准（已验证为空）；
- `VectorService` 初始化的 16.48s 中包含第二次 BGE 实例加载，属正常。

## 7. 新增测试与可复现脚本

### 7.1 默认 skip 的集成测试

`backend/tests/integration/services/test_bge_real.py`（7 个用例）：

```powershell
# 默认：整模块 skip，不下载、不加载模型，不影响全量 pytest / CI
cd backend
..\.venv\Scripts\python.exe -m pytest tests/integration/services/test_bge_real.py -q
# => 7 skipped

# 真实执行（需模型已缓存；RUN_REAL_BGE_OFFLINE=1 追加离线子进程用例）
$env:RUN_REAL_BGE = '1'
$env:RUN_REAL_BGE_OFFLINE = '1'
..\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/services/test_bge_real.py -v
```

| 用例 | 覆盖 |
|------|------|
| `test_model_cache_present` | 权重 ≥50MB、`hidden_size=512`、ST 布局完整 |
| `test_embedder_loads_dimension_512` | 真实加载、dim=512、health_check、非零向量 |
| `test_semantic_similarity_ordering` | 4 组中文语义排序 + USB 组 Δ>0.10 |
| `test_vectors_are_normalized` | norm≈1.0 |
| `test_batch_matches_single` | batch 与单条一致（<1e-5） |
| `test_offline_load_by_repo_id` | `RUN_REAL_BGE_OFFLINE=1` 门槛；离线子进程按 repo id 加载 |
| `test_milvus_joint_index_search` | Milvus 可达时：index(9999)→search 命中→清理 |

默认行为（不设 `RUN_REAL_BGE`）：整模块 **7 skipped in 0.04s**（不下载、不加载模型，
不访问网络）；`pytest -q --collect-only` 全量 **491 tests collected，无 collection error**；
全量 `pytest -q` 实测 **473 passed / 18 skipped / 0 failed（21.52s）**——基线
466 passed / 1 skipped **无回归**（pass 数 +7 来自队友新增的可执行测试，skipped 数增加
来自各任务新增的默认 skip 用例）。

开启门槛后的真实执行结果：**7 passed, 3 warnings in 52.06s**（含离线子进程用例与
Milvus 联检用例；主进程自动强制 `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`，避免 §5.2 的联网挂起）。

### 7.2 端到端脚本

`backend/scripts/verify/bge_embedding_e2e.py`：五阶段（下载/缓存 → 加载 → 语义 →
离线 → Milvus），任意检查失败 exit 1，下载/加载致命失败 exit 2；
支持 `--skip-download` / `--offline` / `--milvus off` / `--stages cache` /
`--log-file` / `--json-out`。本次运行：**exit=0，总耗时 362.4s**。

## 8. 复现命令汇总（从零到证据）

```powershell
cd G:\ai-diagnostic-platform\backend
& ..\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 1) 真实下载（首次，约 90MB，慢时可后台跑）
$env:HF_ENDPOINT = 'https://hf-mirror.com'
& ..\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; print(snapshot_download('BAAI/bge-small-zh-v1.5'))"

# 2) 全链路验证（下载/缓存→加载→语义→离线→Milvus），保留完整日志与结构化证据
& ..\.venv\Scripts\python.exe -X utf8 scripts\verify\bge_embedding_e2e.py `
    --log-file $env:TEMP\bge_e2e_run.log --json-out $env:TEMP\bge_e2e_result.json

# 3) 纯离线复验（断网/无镜像场景）
$env:HF_HUB_OFFLINE = '1'; $env:TRANSFORMERS_OFFLINE = '1'
& ..\.venv\Scripts\python.exe -X utf8 scripts\verify\bge_embedding_e2e.py --offline --skip-download --milvus off

# 4) pytest 门槛测试
$env:RUN_REAL_BGE = '1'; $env:RUN_REAL_BGE_OFFLINE = '1'
& ..\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/services/test_bge_real.py -v
```

## 9. 结论与遗留问题

### 9.1 结论

- **BGE 本地实链路在本地 venv 中已完全打通**：真实下载（hf-mirror）→ 真实加载
  （dim=512）→ 语义质量（4/4 排序正确）→ 离线加载 → Milvus 联合检索命中并清理，
  无任何伪造/回退分支参与。
- 模型可离线部署：缓存落盘后，`HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1` 下
  完全无需外网。
- 新增测试默认 skip，不污染全量 pytest；e2e 脚本可重复运行并输出结构化证据。

### 9.2 遗留问题 / 建议（状态更新）

1. ✅ **已修复（Lead 并行修复，非本任务写入范围）** — `VectorService` 原硬编码 10s
   加载超时，且超时后 `_embedding_load_started` 一次性 latch 导致该进程**永久**回退关键词。
   现实现改为：超时读取 `settings.EMBEDDING_LOAD_TIMEOUT`（默认 30s，Docker 建议 120）；
   共享同一后台加载线程、单次调用超时返回 False 但**后续调用可继续等待/重试**并在成功后
   回填 `_embedding`；新增单测 `backend/tests/unit/services/test_vector_service_embedding_load.py`。
   （原实测依据：冷加载 15.35s > 10s，首次向量请求几乎必然超时。）
2. ✅ **方案已落地（task-9）** — Docker 内真实 BGE 通过新增的
   `deploy/docker-compose.bge.yml` 覆盖文件启用：`INSTALL_ML=true` 构建镜像（含
   torch + sentence-transformers）、`EMBEDDING_PROVIDER=local`、
   `EMBEDDING_LOAD_TIMEOUT=120`、`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`、
   只读挂载 `${HF_CACHE_DIR}:/root/.cache/huggingface:ro`（见 §5.3，`docker compose config`
   断言见附录 C）。同时 `/api/v1/vector/health` 的 `embedding_provider` 已改为返回真实
   provider（`get_embedder().provider_name`，`BGEEmbedder`/`HashingEmbedder` 一目了然），
   并新增 `backend/tests/unit/services/test_vector_health_provider.py`。
   **保留提示**：ML 镜像体积 +2GB 以上、首次构建数分钟～十几分钟；不启用本地 BGE 时
   保持 `INSTALL_ML=false` 精简镜像并配置云端 Embedding API。
3. **「缓存命中仍联网」坑**（§5.2）：建议在部署文档/启动脚本中强制设置
   `HF_HUB_OFFLINE=1`，避免内网环境首次加载挂起。
4. hf-mirror 速度较慢（~200 KB/s），多机部署建议预置缓存/内部镜像，不要每次构建下载。
5. Windows 本地开发 torch import 极慢（Defender），非代码问题；CI/容器无此现象。

## 附录 A：e2e 真实输出摘要（2026-11-12 17:40:28 起，总 362.4s，exit=0）

```text
[1/5] 下载 / 缓存核验
  [PASS] snapshot_download 成功 → 1.56s
  [INFO] 远端 model_info commit → 7999e1d3359715c523056ef9478215996d62a620
  [INFO] 文件数 / snapshot 体积 → 13 个 / 183.34 MiB
  [INFO] repo 目录磁盘占用 → 274.73 MiB
[2/5] 真实加载
  [INFO] import sentence_transformers 耗时 → 138.8s (2.31min)
  [INFO] 冷加载 → 15.35s
  [INFO] 模型维度 → 512
  [PASS] dimension=512 / health_check 通过
  [INFO] 热加载 → 12.28s
[3/5] 语义质量
  [PASS] USB 超时: cos(查询,相近)=0.7881 vs cos(查询,无关)=0.5461 (delta=+0.2419)
  [PASS] 内核 panic: cos(查询,相近)=0.8108 vs cos(查询,无关)=0.5195 (delta=+0.2913)
  [PASS] 网络丢包: cos(查询,相近)=0.8713 vs cos(查询,无关)=0.5433 (delta=+0.3280)
  [PASS] 内存 OOM: cos(查询,相近)=0.7219 vs cos(查询,无关)=0.4418 (delta=+0.2802)
  [PASS] norm≈1.0 → 最大偏差 7.50e-08
  [PASS] batch 与单条一致 → max|diff|=1.04e-07
  [INFO] 首次调用（含 warmup） → 326.3 ms
  [INFO] 单条 embed 平均（n=3） → 137.9 ms/条
  [INFO] batch embed 8 条 → 共 69.7 ms，8.7 ms/条
[4/5] 离线可复现（HF_HUB_OFFLINE=1 + 无效 HF_ENDPOINT 子进程）
  [INFO] 子进程总耗时 → 136.5s
  [PASS] 离线模式仍能按 repo id 加载，dimension=512
  [PASS] 离线模式向量已归一化
[5/5] Milvus 联合真实检索
  [PASS] Milvus 可连接 → version=v2.4.0, collections=['knowledge_docs']
  [INFO] VectorService 初始化耗时 → 16.48s
  [PASS] index_document 成功 → chunks=1, 3.84s
  [PASS] 语义查询命中 doc_id=9999 → rank=#1, score=0.7332
  [PASS] 已清理 doc 9999（query 确认为空）
结论: ✅ 全部检查通过（BGE 真实链路已打通）
```

## 附录 B：本任务产出文件

| 文件 | 说明 |
|------|------|
| `backend/scripts/verify/bge_embedding_e2e.py` | 五阶段可复现验证脚本（含 README 式注释：HF_ENDPOINT / 离线 / Docker 说明） |
| `backend/tests/integration/services/test_bge_real.py` | 7 个默认 skip 的真实 BGE 集成测试（`RUN_REAL_BGE=1` 门槛） |
| `deploy/docker-compose.bge.yml` | **task-9 新增**：Docker 内本地 BGE 部署覆盖文件（INSTALL_ML=true / local BGE / 离线 / 只读缓存挂载），含用法与验收说明 |
| `docs/20-Audit/verification/04-bge.md` | 本报告 |

> 参考运行产物（临时目录，不随仓库提交）：
> `C:\Users\EDY\AppData\Local\Temp\bge_e2e_run.log`、
> `C:\Users\EDY\AppData\Local\Temp\bge_e2e_result.json`。

## 附录 C：Docker 覆盖文件验证真实输出（2026-11-12 18:16）

环境：`docker compose v5.3.0`（Docker Desktop，Windows）；`HF_CACHE_DIR=C:\Users\EDY\.cache\huggingface`。
**按任务约束未构建 ML 镜像、未重启容器**，以下为「不构建即可完成」的配置级验证
（运行期验收项见 §5.3 表格，需在 `INSTALL_ML=true` 构建并重启后执行）。

```text
# 文件编码检查（避免 Windows/PowerShell 管道二次编码）
A encoding: UTF-8 no BOM=True lines=130 bytes=8434 mojibake=[]

# 叠加覆盖文件后 config -q（不构建、不启动）
B docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.bge.yml config -q
  → exit=0；stderr 为空

# 叠加后配置断言（docker compose ... config --format json）
C backend.build.args.INSTALL_ML        = true
C worker.build.args.INSTALL_ML         = true
C backend.environment.EMBEDDING_PROVIDER        = local
C backend.environment.EMBEDDING_LOAD_TIMEOUT    = 120
C backend.environment.HF_HUB_OFFLINE            = 1
C backend.environment.TRANSFORMERS_OFFLINE      = 1
C backend.environment.HF_HOME                   = /root/.cache/huggingface
C backend.volume  type=bind source=C:\Users\EDY\.cache\huggingface target=/root/.cache/huggingface read_only=True
C worker.volume   type=bind source=C:\Users\EDY\.cache\huggingface target=/root/.cache/huggingface read_only=True

# 默认配置对照（仅基础 compose，不叠加 override）
D default build.args.INSTALL_ML                 = false
D default cache_mounts                          = []
D default environment.EMBEDDING_PROVIDER        = auto
D default environment.EMBEDDING_LOAD_TIMEOUT    = 30
D default environment.HF_HUB_OFFLINE            = 0
D default environment.TRANSFORMERS_OFFLINE      = 0

# HF_CACHE_DIR 未设置时（必须显式设置，防止误挂空目录）
E exit=1；required variable HF_CACHE_DIR is missing a value
```

结论：覆盖文件在**不修改基础 compose/Dockerfile** 的前提下，正确注入了
`INSTALL_ML=true`、`EMBEDDING_PROVIDER=local`、`EMBEDDING_LOAD_TIMEOUT=120`、
离线变量与只读缓存挂载；默认配置保持精简（`INSTALL_ML=false`、无缓存挂载）。
