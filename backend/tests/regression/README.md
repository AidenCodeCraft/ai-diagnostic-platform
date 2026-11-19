# 黄金集回归（fast 套件）

## 跑法

```bash
cd backend
# 用导出的样本文件（推荐，CI 用这个）
GOLDEN_SAMPLES_FILE=/path/to/golden_export.json \
MILVUS_ENABLED=true \
python -m pytest tests/regression -m golden -q

# 或直接用库里的 approved 样本（本地/预发）
MILVUS_ENABLED=true python -m pytest tests/regression -m golden -q
```

阈值可用环境变量覆盖：`REGRESSION_RECALL_AT_5`（默认 0.85）、`REGRESSION_MRR`（默认 0.70）。
**下调阈值必须单独提交并走管理员审批**，不允许在 CI 变红时顺手改。

## 数据来源

`GET /api/v1/quality/golden-samples/export` 导出的 JSON（`{"items":[...]}`）。
样本由对话界面「标注为回归样本」提交，经测试/开发/管理员按角色链审核后进入本回归。

## 输出

`backend/reports/golden_report.json`：整体指标 + 每条样本的实际召回列表与名次，
失败样本带完整上下文，可直接定位是召回漏了还是期望写错了。

## 说明

- 本套件只调检索层，不调 LLM：确定性强、零 API 成本，适合每次提交跑；
- 语义正确性（答案是否回答了问题）的判分放在夜间 full 套件，另行接入；
- 没有 approved 样本时整个目录 skip，不会因为"还没标样本"让 CI 变红。
