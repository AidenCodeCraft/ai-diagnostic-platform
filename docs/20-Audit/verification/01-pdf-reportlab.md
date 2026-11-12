# PDF 真实导出验证（reportlab）

- **日期**：2026-11-12
- **执行**：Agent Team 成员 `pdf-reportlab`
- **关联任务**：`task-1` — PDF 真实导出验证（reportlab：本地 venv + Docker 部署镜像 + 接口 200）
- **状态**：本地 venv ✅；Docker 镜像内依赖 ✅；部署端到端 ✅（新镜像重启后真实 HTTP 验证 17/17 通过，2026-11-12 17:20）

## 1. 背景与结论

缺口背景：`GET /api/v1/reports/{report_id}/pdf` 依赖 `reportlab` 做服务端 PDF 渲染
（`backend/app/services/diagnostics/report_service.py::export_pdf`）。本地 venv 已安装
reportlab，但 2 小时前构建的部署镜像未包含该依赖，导致运行中的服务端该接口不可用。

本次完成：

| # | 验证项 | 结论 |
|---|--------|------|
| 1 | 本地 venv 单元测试（`tests/unit/services/test_report_pdf.py`） | ✅ 1 passed, 1 skipped（skip 为「reportlab 缺失」fallback 用例，因已安装而按设计跳过） |
| 2 | 重建后镜像内 `import reportlab` | ✅ backend 与 worker 镜像均为 **reportlab 5.1.0** |
| 3 | 真实 HTTP 全链路导出 PDF（部署服务） | ✅ HTTP 200 / `application/pdf` / `%PDF-1.3` / 3099 bytes / 1 页 / Content-Disposition 正确（二次运行 3095 bytes 同样通过） |
| 4 | 中文字体路径（STSong-Light UnicodeCIDFont） | ✅ 字体资源引用 `/STSong-Light /Type0`，pypdf 可提取中文（部署端 148 chars，本地 58 chars） |
| 5 | 新增默认 skip 的 API 回归测试 | ✅ 默认 2 skipped；`RUN_REAL_PDF_API=1` 时 2 passed |
| 6 | 可复现脚本 | ✅ `backend/scripts/verify/pdf_export_e2e.py`，17/17 校验项通过 |

> 关键结论：**仅“镜像里装上 reportlab”不够**——运行中的容器加载的是旧镜像代码，
> 旧镜像既没有依赖也**没有 `/pdf` 路由**（OpenAPI 中缺失）。必须
> `docker compose build backend worker` 重建镜像 **并重启容器** 后，接口才可用。

## 2. 版本与产物信息

| 项目 | 值 |
|------|-----|
| Python | 3.12.13（项目 venv `G:\ai-diagnostic-platform\.venv`；镜像内同为 3.12-slim） |
| reportlab | **5.1.0**（`backend/requirements.txt:17` 声明 `reportlab>=4.0.0`） |
| pypdf（仅开发期校验，不写入 requirements） | 7.0.1 |
| pytest | 8.3.3（requirements 锁定版本） |
| 重建镜像 | `deploy-backend:latest` = `5e74f47c2c41`；`deploy-worker:latest` = `a85691c71ba1`（982MB，构建完成于 2026-11-12 16:36 前后） |
| 部署容器 | 2026-11-12 17:20 由 Lead 用新镜像重启：`ai-diagnostic-backend` 镜像 ID `sha256:5e74f47c2c41…`（= `deploy-backend:latest`），`/health` ok；`ai-diagnostic-worker` 同为 `deploy-worker:latest` |
| 服务地址 | `http://localhost:8000` |

## 3. 安装 / 重建步骤（可复现）

### 3.1 本地 venv

```powershell
# 项目根目录下（依赖已声明在 backend/requirements.txt:17）
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pip install "reportlab>=4.0.0"
# 仅开发期 PDF 结构校验（可选）：
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pip install pypdf --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3.2 Docker 镜像重建

镜像由 compose 统一定义（`deploy/docker-compose.yml:156-159`、`235-238`，两者共用
`backend/Dockerfile`，Dockerfile 内 `COPY backend/requirements.txt` +
`RUN pip install -r requirements.txt` 自动带上 reportlab）：

```powershell
# 项目根目录下；backend/worker 共用同一 Dockerfile，一次构建两个 tag
docker compose -f deploy/docker-compose.yml build backend worker

# 重建完成后必须重启容器，旧容器仍跑旧镜像（本次由 Lead 统一执行）
docker compose -f deploy/docker-compose.yml up -d --no-deps backend worker
```

### 3.3 镜像 / 运行容器内依赖验证

```powershell
docker run --rm --entrypoint python deploy-backend:latest -c "import reportlab; print(reportlab.Version)"
# -> 5.1.0
docker run --rm --entrypoint python deploy-worker:latest -c "import reportlab; print(reportlab.Version)"
# -> 5.1.0

# 运行中容器内同样确认（重启后）：
docker exec ai-diagnostic-backend python -c "import reportlab; print('reportlab', reportlab.Version)"
# -> reportlab 5.1.0
```

## 4. 真实验证命令与输出摘要

### 4.1 本地 venv 单元测试

```powershell
cd backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/unit/services/test_report_pdf.py -v
```

```text
tests/unit/services/test_report_pdf.py::test_pdf_export_requires_reportlab SKIPPED [ 50%]
tests/unit/services/test_report_pdf.py::test_pdf_export_returns_pdf_bytes PASSED [100%]
======================== 1 passed, 1 skipped in 8.25s =========================
```

说明：`test_pdf_export_requires_reportlab` 是「reportlab 缺失应抛
`ReportExportUnavailable`」的 fallback 用例，`skipif(HAS_REPORTLAB)` 设计如此；
真实导出用例 `test_pdf_export_returns_pdf_bytes` PASS，即本地缺口已消除。

### 4.2 本地 service 级 PDF 结构与字体（pypdf 解析）

用 `ReportService.export_pdf` 渲染一份含中文的报告后，用 pypdf 解析真实产物：

```json
{
  "bytes": 2789,
  "head": "%PDF-1.3",
  "pages": 1,
  "fonts": [["/F1", "/Helvetica", "/Type1"], ["/F2", "/STSong-Light", "/Type0"]],
  "extracted_cjk_chars": 58,
  "extracted_text": "设备 D3C 诊断报告\nSummary:\n设备在凌晨 03:12 出现 USB 控制器通信中断…"
}
```

证据：`/STSong-Light` 以 `/Type0`（CID）字体出现在页面字体资源中，且 pypdf 能正确
提取中文，说明 `UnicodeCIDFont("STSong-Light")` 注册成功、中文渲染路径生效。

### 4.3 部署端到端（真实 HTTP，新镜像重启后）

> 前置（已完成）：Lead 执行镜像重建 + `backend`/`worker` 容器重启。验证时
> `ai-diagnostic-backend` / `ai-diagnostic-worker` 均已运行 `deploy-backend` / `deploy-worker`
> 新镜像（`5e74f47c2c41`），`GET /health` = `{"status":"ok"}`。

```powershell
cd backend
G:\ai-diagnostic-platform\.venv\Scripts\python.exe scripts\verify\pdf_export_e2e.py
```

脚本链路（全部真实 HTTP）：`POST /api/v1/logs/upload` → `POST /api/v1/logs/{id}/parse`
→ `POST /api/v1/analyses/run`（mock LLM）→ `POST /api/v1/reports/{log_id}`
→ `GET /api/v1/reports/{report_id}/pdf`。

首次运行（2026-11-12 17:20:58 开始，真实输出摘要）：

```text
[0/5] 健康检查：GET /health => 200 {"status":"ok"}；OpenAPI 中存在 /api/v1/reports/{report_id}/pdf ✅
[1/5] POST /api/v1/logs/upload          => 200 (155 ms)，log_id=3
[2/5] POST /api/v1/logs/3/parse         => 200 (224 ms)，event_count=8
[3/5] POST /api/v1/analyses/run         => 200 (2124 ms)，status=completed（mock LLM，中文 summary/root_cause）
[4/5] POST /api/v1/reports/3            => 200 (79 ms)，report_id=1
[5/5] GET  /api/v1/reports/1/pdf        => 200 (451 ms, 3099 bytes)
      Content-Type:        application/pdf
      Content-Disposition: attachment; filename="report_1.pdf"
      魔数: b'%PDF-1.3'；页数: 1（pypdf）；STSong 字体: [['/F1','/Helvetica'], ['/F2','/STSong-Light']]
      pypdf 提取中文: 148 chars
校验通过: True（17/17）；总耗时 8796.6 ms
```

二次运行（验证可重复性）：

```text
POST /api/v1/logs/upload   => 200，log_id=4
POST /api/v1/logs/4/parse  => 200，event_count=8
POST /api/v1/analyses/run  => 200 (153 ms)，status=completed
POST /api/v1/reports/4     => 200，report_id=2
GET  /api/v1/reports/2/pdf => 200 (20 ms, 3095 bytes)，1 页
     Content-Disposition: attachment; filename="report_2.pdf"
     字体 [['/F1','/Helvetica'], ['/F2','/STSong-Light']]，中文 148 chars，校验 17/17 通过
```

说明：验证时 Milvus 仍在修复中（容器 unhealthy），但 `analyses/run` **未失败**
（200 / completed，2.1s）：VectorService 自动退化为关键词检索，summary 中
“知识库命中了相关文档…”即知识库检索结果——说明 PDF 链路不依赖 Milvus。
PDF 已保存至 `%TEMP%\pdf_e2e_*\report_1.pdf` 供人工核对。

独立复核（curl 直接取运行中已有报告 `report_1` 的 PDF，2026-11-12 17:22）：

```text
$ curl.exe -s -D - -o NUL http://localhost:8000/api/v1/reports/1/pdf
HTTP/1.1 200 OK
content-disposition: attachment; filename="report_1.pdf"
content-length: 3099
content-type: application/pdf
（其余为安全响应头：x-frame-options/x-content-type-options/CSP 等）

落盘复核：3099 bytes，魔数 %PDF-1.3，pypdf 解析 1 页；运行中容器
`docker exec ai-diagnostic-backend python -c "import reportlab; print(reportlab.Version)"` -> 5.1.0
```

### 4.4 新增回归测试（默认 skip）

`backend/tests/integration/api/test_report_pdf_api.py`：

```powershell
# 默认：全量 pytest 收集时整模块 skip，不污染基线
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/integration/api/test_report_pdf_api.py -v
# => 2 skipped in 0.59s

# 显式开启：真实 PDF API 回归
$env:RUN_REAL_PDF_API="1"
G:\ai-diagnostic-platform\.venv\Scripts\python.exe -m pytest tests/integration/api/test_report_pdf_api.py -v
# => 2 passed in 2.74s
Remove-Item Env:\RUN_REAL_PDF_API
```

测试用 `TestClient` + 内存 SQLite（不依赖外部服务），覆盖缺口：
API 层 200/Content-Type/%PDF/大小/页数/Content-Disposition/STSong 字体断言，
以及「不存在报告 → 404」。

### 4.5 脚本自检（本地 uvicorn 干跑，先于部署验证）

在不依赖容器的情况下用 venv 起本地 uvicorn（`127.0.0.1:18080`，SQLite 文件库、
`MILVUS_ENABLED=false`、mock LLM）跑同一脚本，验证脚本本身可复现：

```text
POST /api/v1/logs/upload => 200 (47 ms)
POST /api/v1/logs/1/parse => 200，event_count=8
POST /api/v1/analyses/run => 200，status=completed
POST /api/v1/reports/1 => 200，report_id=1
GET  /api/v1/reports/1/pdf => 200 (880 ms, 3030 bytes)
  Content-Type: application/pdf
  Content-Disposition: attachment; filename="report_1.pdf"
  %PDF-1.3, 1 页, 字体 [['/F1','/Helvetica'], ['/F2','/STSong-Light']], 中文 131 chars
校验通过: True（17/17），总耗时 2649 ms
```

## 5. 踩坑与注意事项

1. **“装依赖”≠“接口可用”**：旧运行容器既缺 reportlab，也缺 `/pdf` 路由（旧镜像代码早于
   本次改动）。实测旧容器 `GET /openapi.json` 中没有 `/api/v1/reports/{report_id}/pdf`，
   此时 e2e 脚本在路由检查步即失败——必须先重建镜像并重启容器，不能只 `pip install` 进容器。
2. **不要并发重复构建**：镜像构建耗时长且占资源；确认 `docker images deploy-backend`
   的 `CreatedSince` 已更新且容器 `Image` ID 与新镜像一致后即可停手。
3. **reportlab 是可选依赖、代码有回退**：`export_pdf` 在 reportlab 缺失时抛
   `ReportExportUnavailable`（API 映射 501）；`STSong-Light` 注册失败会静默回退 Helvetica
   （中文将不可读）。因此测试/脚本同时断言 **HTTP 200** 且 **字体资源出现 STSong**，
   避免“回退成功但中文乱码”被漏检。
4. **pypdf 只用于开发期校验**：未写入 `requirements.txt`（镜像无需它）；测试与脚本对
   pypdf 做可选导入，缺失时页数退化为原始字节统计、字体用原始字节 `b"STSong"` 判定。
5. **中文终端输出**：Windows 控制台默认代码页可能把中文打乱码，脚本内已强制
   `stdout.reconfigure(encoding="utf-8")`；手工执行建议 `$env:PYTHONIOENCODING="utf-8"`。
6. **脚本运行产物不落仓库**：PDF 写入系统临时目录（或 `E2E_KEEP_PDF` 指定目录），
   不污染 workspaces。

## 6. 改动文件（写入范围内）

| 文件 | 说明 |
|------|------|
| [`backend/scripts/verify/pdf_export_e2e.py`](../../../backend/scripts/verify/pdf_export_e2e.py) | 真实 HTTP 全链路验证脚本，打印状态码/头/大小/页数/字体证据与 `EVIDENCE_JSON`，可重复运行 |
| [`backend/tests/integration/api/test_report_pdf_api.py`](../../../backend/tests/integration/api/test_report_pdf_api.py) | API 级 PDF 回归测试，默认 skip，`RUN_REAL_PDF_API=1` 才执行 |
| `docs/20-Audit/verification/01-pdf-reportlab.md` | 本报告 |

未修改 `deploy/`、compose、容器配置或他人文件；未 git commit。

## 7. 遗留与风险

1. **部署端到端已完成**（2026-11-12 17:20）：新镜像重启后真实 HTTP 全链路 17/17 通过，
   一次运行 3099 bytes / 1 页，二次运行 3095 bytes / 1 页，均 HTTP 200 且中文字体生效。
2. **验证时 Milvus 不可用不影响本条链路**：`analyses/run` 在 Milvus unhealthy 情况下仍
   200/completed（VectorService 退化关键词检索）；PDF 链路不依赖 Milvus，无需等待其修复。
   现象已按 Lead 要求记录于此。
3. **worker 容器 health 状态**：重启后 worker 显示 `unhealthy`（与本任务无关，属既有问题，
   由 Lead/其他成员跟进）；worker 镜像内 reportlab 已验证可导入（5.1.0）。
4. **版本未锁死**：`requirements.txt` 为 `reportlab>=4.0.0`，现装 5.1.0；如需可复现构建建议
   后续锁定精确版本（本次按任务范围未改 requirements）。
5. **全量 pytest 基线**：本任务新增测试默认 skip（`--collect-only` 全量收集 474 项无 import 错误），
   不影响原 466 passed / 1 skipped 基线；由 Lead 统一跑全量确认。
