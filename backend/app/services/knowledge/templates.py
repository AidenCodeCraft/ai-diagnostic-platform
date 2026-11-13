"""知识库模板契约 — 四类内容的标准章节与必填级别。

类型：
  - case        现场问题处理示例（诊断证据来源）
  - faq         FAQ（参考 + 日志关键字定位）
  - code_logic  代码逻辑（判断提问依据 / 纠错）
  - knowledge   基础知识（判断提问依据 / 常识校验）

级别（level）：
  - required     必填，缺失/为空 → 不能 active
  - recommended  建议，缺失 → 提示但不阻断
  - optional     可选
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


LEVEL_REQUIRED = "required"
LEVEL_RECOMMENDED = "recommended"
LEVEL_OPTIONAL = "optional"


@dataclass(frozen=True)
class SectionSpec:
    key: str
    title: str
    level: str = LEVEL_OPTIONAL
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeTemplate:
    doc_type: str
    name: str
    sections: Tuple[SectionSpec, ...] = ()
    free_form: bool = False
    skeleton: str = ""   # 新建时预填的规则模板
    guide: str = ""      # 格式说明（一句话）
    example: str = ""    # 可参考的填写示例


# 通用子节别名（用于「日志特征」下的 ### 关键词/正则/排除正则）
COMMON_SECTION_ALIASES: Dict[str, str] = {
    "关键词": "log_keywords",
    "关键字": "log_keywords",
    "正则": "log_patterns",
    "正则表达式": "log_patterns",
    "排除正则": "negative_patterns",
    "排除": "negative_patterns",
}


# ----------------------------------------------------------------------
# 新建预填骨架 / 格式说明 / 填写示例
# ----------------------------------------------------------------------

CASE_SKELETON = """## 现象

（请描述现象：设备型号、软件版本、触发操作、具体表现）

## 特征点

- 城市：
- 设备类型：
- 版本：

## 原因

（请说明根因或判断依据；不确定时写“待确认”）

## 处理结果

（请说明处理步骤与最终结果）

## 日志特征

### 关键词

- 

### 正则

- 
"""

FAQ_SKELETON = """## 现象

（请描述用户遇到的现象）

## 分析

（请说明原因与分析过程）

## 关键字

- 

## 关键字解释

- 
"""

CODE_LOGIC_SKELETON = """## 逻辑说明

（请说明模块/函数的作用、触发条件与关键分支）

## 关键流程

1. 

## 注意事项

- 
"""

KNOWLEDGE_SKELETON = """## 概述

（请说明该知识点的定义与适用范围）

## 详细说明

- 

## 参考资料

- 
"""

CASE_GUIDE = "按「现象 → 特征点 → 原因 → 处理结果 → 日志特征」填写；日志特征用于后续自动定位日志。"

FAQ_GUIDE = "按「现象 → 分析 → 关键字 → 关键字解释」填写；关键字用于知识检索与日志匹配。"

CODE_LOGIC_GUIDE = "建议按「逻辑说明 → 关键流程 → 注意事项」分节，用于判断提问中的逻辑是否成立。"

KNOWLEDGE_GUIDE = "建议按「概述 → 详细说明 → 参考资料」分节，用于回答常识性问题并纠正错误认知。"

CASE_EXAMPLE = """## 现象

潜江 D3C 设备（V2.1）紧急报警上传视频失败，部分车辆正常、部分不上传。

## 特征点

- 城市：潜江
- 设备类型：D3C
- 版本：V2.1

## 原因

平台下发 9206 文件上传命令后，录像未写盘，返回 -5007。

## 处理结果

确认司机是否手动触发命令；检查录像写盘状态与 9206 下发链路后恢复正常。

## 日志特征

### 关键词

- 紧急报警
- 9206
- -5007

### 正则

- (?i)9206
"""

FAQ_EXAMPLE = """## 现象

日志中出现 `usb timeout` 或 `device not responding`。

## 分析

优先检查线缆与供电，其次确认设备描述符读取是否失败。

## 关键字

usb timeout、not responding、descriptor

## 关键字解释

- usb timeout：USB 传输超时，通常与线缆/供电/驱动有关。
- not responding：设备无响应，检查枚举与固件状态。
"""

CODE_LOGIC_EXAMPLE = """## 逻辑说明

视频上传模块收到 9206 命令后，先校验录像是否已写盘，再发起上传。

## 关键流程

1. 接收 9206 指令并解析文件 ID。
2. 检查录像写盘状态。
3. 未写盘返回 -5007，否则启动上传任务。

## 注意事项

- 9206 由平台下发，需与平台版本配合。
"""


KNOWLEDGE_EXAMPLE = """## 概述

USB 2.0 理论速率 480 Mbps，USB 3.0 理论速率 5 Gbps；实际吞吐受线缆、控制器与设备能力影响。

## 详细说明

- USB 2.0 常见于键盘、鼠标等低速外设。
- USB 3.0 接口通常为蓝色，适合高速存储与视频采集。

## 参考资料

- USB-IF 官方规范
"""


TEMPLATES: Dict[str, KnowledgeTemplate] = {
    "case": KnowledgeTemplate(
        doc_type="case",
        name="现场问题处理示例",
        sections=(
            SectionSpec("symptom", "现象", LEVEL_REQUIRED, ("问题现象", "问题描述", "现象描述")),
            SectionSpec("features", "特征点", LEVEL_RECOMMENDED, ("适用环境", "环境", "特征")),
            SectionSpec("root_cause", "原因", LEVEL_REQUIRED, ("根因", "原因分析", "根因分析")),
            SectionSpec("solution", "处理结果", LEVEL_REQUIRED, ("解决方案", "处理方法", "解决方式")),
            SectionSpec("log_signature", "日志特征", LEVEL_RECOMMENDED, ("日志关键字", "日志定位", "日志特征与定位")),
            SectionSpec("related", "关联知识", LEVEL_OPTIONAL, ("关联", "相关知识")),
            SectionSpec("images", "相关图片", LEVEL_OPTIONAL, ("图片", "截图")),
        ),
        skeleton=CASE_SKELETON,
        guide=CASE_GUIDE,
        example=CASE_EXAMPLE,
    ),
    "faq": KnowledgeTemplate(
        doc_type="faq",
        name="FAQ",
        sections=(
            SectionSpec("symptom", "现象", LEVEL_REQUIRED, ("问题现象", "问题描述")),
            SectionSpec("analysis", "分析", LEVEL_REQUIRED, ("原因", "原因分析", "分析过程")),
            SectionSpec("keywords", "关键字", LEVEL_REQUIRED, ("关键词",)),
            SectionSpec("keyword_explain", "关键字解释", LEVEL_REQUIRED, ("关键字解析", "关键词解释", "关键字说明")),
            SectionSpec("examples", "示例", LEVEL_OPTIONAL),
            SectionSpec("author", "作者", LEVEL_OPTIONAL),
        ),
        skeleton=FAQ_SKELETON,
        guide=FAQ_GUIDE,
        example=FAQ_EXAMPLE,
    ),
    "code_logic": KnowledgeTemplate(
        doc_type="code_logic",
        name="代码逻辑",
        free_form=True,
        sections=(
            SectionSpec("log_signature", "日志特征", LEVEL_OPTIONAL, ("日志关键字",)),
            SectionSpec("related", "关联知识", LEVEL_OPTIONAL, ("相关知识",)),
        ),
        skeleton=CODE_LOGIC_SKELETON,
        guide=CODE_LOGIC_GUIDE,
        example=CODE_LOGIC_EXAMPLE,
    ),
    "knowledge": KnowledgeTemplate(
        doc_type="knowledge",
        name="基础知识",
        free_form=True,
        sections=(
            SectionSpec("log_signature", "日志特征", LEVEL_OPTIONAL, ("日志关键字",)),
            SectionSpec("related", "关联知识", LEVEL_OPTIONAL, ("相关知识",)),
        ),
        skeleton=KNOWLEDGE_SKELETON,
        guide=KNOWLEDGE_GUIDE,
        example=KNOWLEDGE_EXAMPLE,
    ),
}


def get_template(doc_type: Optional[str]) -> Optional[KnowledgeTemplate]:
    return TEMPLATES.get((doc_type or "").strip().lower())


def guess_section_key(title: str) -> str:
    """按章节标题猜测其模板键（跨所有模板的别名）。"""
    title = (title or "").strip()
    if not title:
        return ""
    for template in TEMPLATES.values():
        for spec in template.sections:
            if spec.title == title or title in spec.aliases:
                return spec.key
    return COMMON_SECTION_ALIASES.get(title, "")


def build_alias_map(template: Optional[KnowledgeTemplate]) -> Dict[str, str]:
    """标题/别名 → 章节键。"""
    alias_map: Dict[str, str] = {}
    if template is None:
        return dict(COMMON_SECTION_ALIASES)
    for spec in template.sections:
        alias_map[spec.title] = spec.key
        for alias in spec.aliases:
            alias_map[alias] = spec.key
    for title, key in COMMON_SECTION_ALIASES.items():
        alias_map.setdefault(title, key)
    return alias_map


def list_templates() -> List[Dict]:
    """返回全部模板契约（供前端加载）。"""
    return [
        {
            "doc_type": t.doc_type,
            "name": t.name,
            "free_form": t.free_form,
            "skeleton": t.skeleton,
            "guide": t.guide,
            "example": t.example,
            "sections": [
                {"key": s.key, "title": s.title, "level": s.level, "aliases": list(s.aliases)}
                for s in t.sections
            ],
        }
        for t in TEMPLATES.values()
    ]
