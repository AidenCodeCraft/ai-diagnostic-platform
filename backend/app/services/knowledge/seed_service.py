"""知识库种子数据服务。

覆盖四类内容：case / faq / code_logic / knowledge。
可通过脚本 `python -m scripts.seed_knowledge` 或管理接口 `POST /admin/knowledge/seed` 调用。
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.knowledge.document_meta_service import (
    KnowledgeDocumentMetaService,
    KnowledgeSectionService,
)
from app.services.knowledge.format_service import KnowledgeFormatService
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.knowledge.profile_service import KnowledgeProfileService
from app.services.knowledge.section_parser import SectionParser

SAMPLE_DOCS: List[Dict[str, Any]] = [
    {
        "title": "潜江 D3C 紧急报警上传异常",
        "category": "现场问题",
        "doc_type": "case",
        "content": """# 潜江 D3C 紧急报警上传异常

## 现象

潜江的 D3C 设备，同样版本，有的车“紧急报警”上传视频，有的不上传。

## 原因

上报司机手动命令:1 后平台下发 9206 文件上传，录像未写盘导致 -5007。

## 处理结果

平台处理：确认司机是否手动触发命令，检查录像写盘状态与 9206 下发链路。

## 特征点

城市: 潜江
设备类型: D3C
版本: V2.1

## 日志特征

### 关键词

- 紧急报警
- 9206
- -5007

### 正则

- (?i)9206
""",
    },
    {
        "title": "日志出现 usb timeout 如何排查",
        "category": "FAQ",
        "doc_type": "faq",
        "content": """# 日志出现 usb timeout 如何排查

## 现象

日志中出现 `usb timeout` / `device not responding` 等关键字。

## 分析

优先检查 USB 线缆与供电，其次确认设备描述符读取是否失败。

## 关键字

usb timeout、not responding、descriptor

## 关键字解释

- usb timeout：USB 传输超时，通常与线缆/供电/驱动有关。
- not responding：设备无响应，检查枚举与固件状态。
""",
    },
    {
        "title": "视频上传模块 9206 命令处理逻辑",
        "category": "代码逻辑",
        "doc_type": "code_logic",
        "content": """# 视频上传模块 9206 命令处理逻辑

9206 命令由平台下发，用于触发指定文件上传。

处理流程：

1. 接收 9206 指令并解析文件 ID；
2. 检查录像是否已写盘；
3. 未写盘则返回 -5007；
4. 写盘完成则启动上传任务。
""",
    },
    {
        "title": "USB 3.0 与 USB 2.0 速率差异说明",
        "category": "基础知识",
        "doc_type": "knowledge",
        "content": """# USB 3.0 与 USB 2.0 速率差异说明

USB 2.0 理论速率 480 Mbps，USB 3.0 为 5 Gbps。

实际吞吐受线缆质量、控制器与设备能力共同影响。
""",
    },
]


def standardize_document(db, doc_id: int) -> None:
    """入库规范化（与 API 层一致）：内容规范化、分节、元信息、诊断剧本、向量索引。"""
    doc = KnowledgeService(db).get(doc_id)
    fmt = KnowledgeFormatService().preview(doc.content or "", doc.doc_type, doc.title)

    doc.content = fmt["normalized_content"]
    doc.status = fmt["status_hint"]
    db.commit()
    db.refresh(doc)

    parsed = SectionParser.parse(doc.content or "", doc.doc_type)
    KnowledgeSectionService(db).replace(doc_id, parsed)
    KnowledgeDocumentMetaService(db).upsert(doc_id, {
        "template_key": doc.doc_type,
        "quality_score": fmt["quality_score"],
        "content_hash": KnowledgeDocumentMetaService.compute_hash(doc.content or ""),
        "features": fmt["features"],
    })

    merged = dict(fmt["profile_draft"])
    meaningful = any(
        merged.get(k) for k in ("symptom", "log_keywords", "log_patterns", "root_cause", "solution")
    )
    if meaningful:
        merged["status"] = "draft" if doc.status == "draft" else "active"
        merged["source"] = "template"
        KnowledgeProfileService(db).upsert(doc_id, merged)

    # 规范化后内容已变化，重新同步向量索引（Milvus 启用时）
    KnowledgeService(db).reindex(doc_id, doc.content or "")


def seed(db, reset: bool = False) -> Dict[str, int]:
    """写入示例知识，返回 {created, skipped, deleted}。"""
    from app.models import KnowledgeDocument

    service = KnowledgeService(db)
    stats = {"created": 0, "skipped": 0, "deleted": 0}

    def find_by_title(title: str):
        return (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.title == title)
            .first()
        )

    if reset:
        for item in SAMPLE_DOCS:
            existing = find_by_title(item["title"])
            if existing is not None:
                service.delete(int(existing.id))
                stats["deleted"] += 1

    for item in SAMPLE_DOCS:
        if find_by_title(item["title"]) is not None:
            stats["skipped"] += 1
            continue
        doc = service.create({
            "title": item["title"],
            "content": item["content"],
            "category": item["category"],
            "doc_type": item["doc_type"],
            "source": "seed",
        })
        standardize_document(db, int(doc.id))
        stats["created"] += 1
    return stats
