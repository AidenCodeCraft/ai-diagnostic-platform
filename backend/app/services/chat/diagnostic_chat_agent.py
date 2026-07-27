"""Diagnostic Chat Agent — 对话预处理管道 + 严格 RAG 知识注入。

非日志对话的完整处理链路：
  Stage 1: 输入清洗 → 去噪、规范化
  Stage 2: 问题分析 → 提取实体、意图、子问题
  Stage 3: RAG 强制检索 → 搜索私域知识库，作为唯一事实来源
  Stage 4: Prompt 组装 → 严格约束 LLM 只重组知识库内容，禁止编造

关键原则：
  - 原始用户输入绝不直接到达 LLM
  - 诊断类问题的回答必须 100% 来源于知识库
  - LLM 角色仅限于语言重组，不是知识创造者
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.rag.rag_prompt import (
    RAG_STRICT_SYSTEM_PROMPT,
)
from app.services.chat.proactive_questioning import (
    check_and_generate_proactive_questions,
    analyze_and_ask_with_llm,
    ProactiveQuestioning,
    UserExpertiseLevel,
)

# 输入长度限制
MAX_INPUT_LENGTH = 4000

# ==================================================================
# 诊断问题判断 —— 多因子加权评分机制
# ==================================================================
# 触发严格 RAG 的最低分数阈值
DIAGNOSTIC_SCORE_THRESHOLD = 2

# 关键词分类（带权重）—— 按类别组织，权重越高越可能是诊断问题
# 症状类 3 分 > 故障类 2 分 > 组件/意图类 1 分
KEYWORD_CATEGORIES = [
    # 症状关键词（权重 3）—— 用户描述了具体异常现象
    (3, [
        "死机", "黑屏", "蓝屏", "花屏", "闪退", "卡死", "卡顿",
        "重启", "自动重启", "无限重启", "无法开机", "不开机",
        "无响应", "没反应", "不亮", "不显示", "没声音", "没画面",
        "发热", "过热", "烫手", "耗电快", "掉电", "电池鼓包",
        "重启循环", "bootloop", "freeze", "stuck", "hang",
    ]),
    # 故障类关键词（权重 2）—— 用户描述了技术性问题
    (2, [
        "错误", "报错", "异常", "失败", "故障", "崩溃",
        "超时", "断连", "掉线", "连不上", "无法连接",
        "不工作", "不能用", "无法使用", "不好使", "失灵",
        "error", "crash", "panic", "failed", "failure", "fault",
        "timeout", "bug", "defect", "corrupt", "damage",
        "不录像", "不录音", "不识别", "不检测", "不触发",
    ]),
    # 组件/系统关键词（权重 1）—— 提到了技术组件或子系统
    (1, [
        "日志", "log", "kernel", "驱动", "driver", "硬件", "固件",
        "firmware", "bios", "uefi", "cpu", "gpu", "内存", "memory",
        "磁盘", "硬盘", "ssd", "hdd", "网络", "wifi", "蓝牙",
        "bluetooth", "usb", "i2c", "spi", "uart", "gpio",
        "电源", "power", "电压", "voltage", "时钟", "clock",
        "传感器", "sensor", "摄像头", "camera", "屏幕", "屏",
        "系统", "system", "进程", "process", "服务", "service",
        "dmesg", "syslog", "串口", "serial", "寄存器", "register",
        "中断", "interrupt", "dma", "pcie", "sata",
        "录像", "编码", "解码", "码流", "帧率", "分辨率",
    ]),
    # 诊断意图关键词（权重 1）—— 用户明确请求诊断/分析
    (1, [
        "诊断", "分析", "排查", "定位", "修复", "解决",
        "什么原因", "为什么", "怎么回事", "怎么办", "如何处理",
        "帮我看看", "帮我看一下", "检查一下",
        "debug", "troubleshoot", "diagnose", "analyze",
    ]),
]

# 非诊断模式 —— 这些前缀/模式匹配时直接判定为非诊断
NON_DIAGNOSTIC_PATTERNS = [
    r"^(你好|hi|hello|嘿|嗨)[\s!！。.,，]*$",
    r"^(谢谢|感谢|多谢|thanks?|thank)[\s!！。.,，]*$",
    r"^(再见|拜拜|bye|goodbye)[\s!！。.,，]*$",
    r"^(你是谁|你叫什么|你能做什么|你的功能|介绍一下)",
    r"^(帮助|help|使用说明|怎么用|使用方法)",
]

# 无害输入黑名单（拒绝处理的模式）
REFUSE_PATTERNS = [
    r"^[!！?？…\.\s,，。、]+$",
    r"^(test|测试|123|abc|asdf)+$",
]


class DiagnosticChatAgent:
    """对话预处理与增强代理。

    接管所有非日志对话流程，确保：
    - 原始用户输入经过清洗、分析和知识增强
    - 绝不将原始文本直接传给 LLM
    - 所有输出都包含结构化上下文
    """

    SYSTEM_BASE = (
        "你是一个专业的设备日志诊断助手。"
        "请根据对话历史、知识库资料和分析结果，帮助用户诊断设备问题。"
        "使用 Markdown 格式回复，引用相关资料时注明来源。"
    )

    GUIDING_HINT = (
        "（如果用户描述不够具体，请在回答末尾用一两句引导用户补充设备型号、故障现象等关键信息。）"
    )

    def __init__(self, db: Session, provider_name: str = "mock"):
        self.db = db
        self.provider_name = provider_name
        self.knowledge = KnowledgeService(db)
        self.references: List[Dict[str, Any]] = []

    # ==================================================================
    # Pipeline Entry
    # ==================================================================

    def enrich_messages(
        self,
        session_id: int,
        user_message: str,
        existing_messages: List[Dict[str, str]],
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """完整预处理管道。

        核心原则：
          - 始终搜索知识库（不论问题类型）
          - 知识库有匹配 → 严格 RAG 模式（LLM 只能重组知识库内容）
          - 知识库无匹配 → 通用对话模式（LLM 自由回复）
          - 支持主动追问：检测缺失关键信息并引导用户
        """
        # Stage 1: 输入清洗
        cleaned = self._sanitize(user_message)
        if self._should_refuse(cleaned):
            return self._build_refusal_response(existing_messages, cleaned)

        # Stage 2: 问题分析（提取实体和子问题）
        analysis = self._analyze_question(cleaned)

        # Stage 2.5: 主动追问检测（增强版，支持 LLM 增强分析）
        if analysis.get("is_diagnostic") and not log_analysis:
            # 尝试 LLM 增强追问分析，失败时回退到关键词分析
            try:
                proactive_llm = analyze_and_ask_with_llm(cleaned, existing_messages)
                if proactive_llm.get("should_ask") and proactive_llm.get("response"):
                    # 记录用户水平以便后续追问中调整策略
                    return existing_messages + [
                        {"role": "assistant", "content": proactive_llm["response"]}
                    ]
            except Exception:
                pass

            # 回退：关键词追问
            proactive_response = check_and_generate_proactive_questions(
                cleaned,
                existing_messages,
                use_llm=False,
            )
            if proactive_response:
                return existing_messages + [
                    {"role": "assistant", "content": proactive_response}
                ]

        # Stage 3: 始终检索知识库（references 存入 self.references 供外层读取）
        knowledge_context, _ = self._retrieve_knowledge(cleaned, analysis)

        # Stage 4: Prompt 组装
        # 关键：是否走严格 RAG 取决于「知识库有没有匹配」，不取决于关键词分类
        if knowledge_context:
            return self._assemble_rag_mode(
                existing_messages, cleaned_input=cleaned,
                knowledge_context=knowledge_context,
                log_analysis=log_analysis,
            )
        else:
            return self._assemble_chat_mode(
                existing_messages, cleaned_input=cleaned,
                analysis=analysis,
                log_analysis=log_analysis,
            )

    # ==================================================================
    # Stage 1: 输入清洗
    # ==================================================================

    def _sanitize(self, text: str) -> str:
        """清洗用户输入：去噪、规范化、截断。

        - 移除控制字符和不可见字符
        - 规范化空白
        - 限制最大长度
        """
        if not text:
            return ""

        # 移除控制字符（保留换行和常用空白）
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        # 合并连续空白行
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        # 去除首尾空白
        cleaned = cleaned.strip()
        # 限制长度
        if len(cleaned) > MAX_INPUT_LENGTH:
            cleaned = cleaned[:MAX_INPUT_LENGTH] + "…(输入过长已截断)"

        return cleaned

    def _should_refuse(self, text: str) -> bool:
        """判断是否为应拒绝的无害输入。"""
        if not text.strip():
            return True
        for pattern in REFUSE_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        return False

    # ==================================================================
    # Stage 2: 问题分析
    # ==================================================================

    def _analyze_question(self, text: str) -> Dict[str, Any]:
        """多因子加权评分判断问题类型。

        评分规则：
          - 症状关键词出现：+3 分/个
          - 故障关键词出现：+2 分/个
          - 组件/意图关键词出现：+1 分/个
          - 不同权重累计叠加

        判定：
          is_diagnostic = 总分 >= DIAGNOSTIC_SCORE_THRESHOLD (2)

        示例：
          "设备黑屏了" → "黑屏"(3分) → is_diagnostic=True
          "你好" → 无匹配 → is_diagnostic=False
          "帮我分析一下日志中的timeout错误" → "分析"(1) + "日志"(1) + "timeout"(2) + "错误"(2) = 6 → True
          "今天天气怎么样" → 无匹配 → is_diagnostic=False
        """
        text_lower = text.lower()

        # 快速路径：非诊断模式直接返回
        for pattern in NON_DIAGNOSTIC_PATTERNS:
            if re.match(pattern, text_lower):
                return {
                    "is_diagnostic": False,
                    "is_simple": True,
                    "score": 0,
                    "matched_keywords": [],
                    "topics": [],
                    "sub_questions": [],
                }

        # 多因子加权评分
        total_score = 0
        matched: list[str] = []
        for weight, keywords in KEYWORD_CATEGORIES:
            for kw in keywords:
                if kw in text_lower:
                    total_score += weight
                    matched.append(kw)

        is_diagnostic = total_score >= DIAGNOSTIC_SCORE_THRESHOLD

        # 极简输入判断
        is_simple = len(text) <= 5 or any(
            text_lower.startswith(p) for p in ["你好", "在吗", "hello", "hi"]
        )

        # 提取主题实体
        topics: list[str] = []
        cn_words = re.findall(r"[\u4e00-\u9fff]{2,5}", text)
        topics.extend(cn_words[:8])
        en_terms = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)
        topics.extend(en_terms[:4])

        # 子问题分解
        sub_questions = self._decompose(text)

        return {
            "is_diagnostic": is_diagnostic,
            "is_simple": is_simple,
            "score": total_score,
            "matched_keywords": matched[:10],
            "topics": topics,
            "sub_questions": sub_questions,
        }

    def _decompose(self, text: str) -> list[str]:
        """将复合问题分解为子问题列表。"""
        # 按中文/英文问号分割
        parts = re.split(r"[？?\n]", text)
        parts = [p.strip() for p in parts if p.strip()]
        # 如果分区后只有 1 个，尝试按序号分割
        if len(parts) == 1:
            sub = re.split(r"(?:^|\n)\s*(?:\d+[.、]|[一二三四五六七八九十]+[、.])", text)
            sub = [s.strip() for s in sub if s.strip()]
            if len(sub) > 1 and not sub[0].startswith(("1", "一")):
                # 移除前置引导语（如"请帮我："）
                parts = sub
        return parts[:5]

    # ==================================================================
    # Stage 3: 知识检索
    # ==================================================================

    def _retrieve_knowledge(
        self, text: str, analysis: Dict[str, Any],
    ) -> tuple[str, List[Dict[str, Any]]]:
        """搜索知识库——智能提取搜索关键词，而非用整句自然语言。

        策略：
          1. 从用户输入中剥离冗余指令（"帮我搜一下""查找知识库"等）
          2. 用提取的主题实体 + 匹配关键词构建搜索词
          3. 多个关键词轮流尝试，取最佳匹配
        """
        if not text.strip():
            return "", []

        # 提取搜索关键词：剥离指令前缀 + 用主题词构建查询
        search_terms = self._extract_search_terms(text, analysis)

        if not search_terms:
            return "", []

        # 尝试多个搜索词的组合
        all_items: list[dict] = []
        seen_ids: set[int] = set()

        for term in search_terms[:3]:  # 最多尝试 3 个搜索词
            try:
                result = self.knowledge.search(term, page_size=5)
                items = result.get("items", [])
                for item in items:
                    if item.get("id") not in seen_ids:
                        seen_ids.add(item["id"])
                        all_items.append(item)
            except Exception:
                continue

            if len(all_items) >= 5:
                break

        if not all_items:
            return "", []

        # 去重并按相关度排序
        all_items.sort(key=lambda d: float(d.get("relevance_score", 0) or 0), reverse=True)
        items = all_items[:5]

        self.references = []
        lines = []
        for i, item in enumerate(items):
            title = item.get("title", "Untitled")
            snippet = item.get("snippet", "")[:300]
            score = item.get("relevance_score", 0)
            if score > 0.1:
                lines.append(
                    f"{i + 1}. **{title}** (相关度: {score:.0%})\n   {snippet}"
                )
                self.references.append({
                    "id": item.get("id"),
                    "title": title,
                    "source": item.get("source") or "知识库",
                    "excerpt": snippet,
                })

        return "\n\n".join(lines) if lines else "", self.references

    def _extract_search_terms(
        self, text: str, analysis: Dict[str, Any],
    ) -> list[str]:
        """从自然语言中提取真正的搜索关键词，剥离指令性冗余。

        例：
          "帮我搜一下知识库里面的内容，关于超速逻辑的"
          → ["超速逻辑", "超速", "超速 逻辑"]

          "L13C设备不录像是什么原因"
          → ["L13C 不录像", "L13C", "不录像", "L13C 录像 原因"]
        """
        cleaned = text.strip()

        # 剥离常见的指令性前缀
        instruction_prefixes = [
            r"^帮我搜(?:一下|索)?(?:知识库|资料|文档)?(?:里面|中)?(?:的)?(?:内容|信息|资料)?[，,。.\s]*",
            r"^(?:请)?(?:帮我)?(?:查找|搜索|检索|查一下|搜一下)(?:知识库|资料|文档)?(?:里面|中)?(?:的)?(?:内容|信息|资料)?[，,。.\s]*",
            r"^(?:关于|有关)[，,。.\s]*",
        ]
        for pattern in instruction_prefixes:
            cleaned = re.sub(pattern, "", cleaned, count=1)

        # 剥离常见的指令性后缀
        instruction_suffixes = [
            r"[，,。.\s]*(?:的内容|的信息|的资料|相关(?:内容|信息|资料))(?:[吗呢吧]?[？?！!]*)?$",
        ]
        for pattern in instruction_suffixes:
            cleaned = re.sub(pattern, "", cleaned)

        cleaned = cleaned.strip()

        # 构建搜索词列表（按优先级）
        terms: list[str] = []

        # 优先级1：剥离后的完整 cleaned query（如果有意义）
        if len(cleaned) >= 2 and cleaned not in ("的", "了"):
            terms.append(cleaned)

        # 优先级2：提取的主题实体组合
        topics = analysis.get("topics", [])
        if len(topics) >= 2:
            terms.append(" ".join(topics[:3]))
        elif len(topics) == 1:
            terms.append(topics[0])

        # 优先级3：匹配的关键词
        keywords = analysis.get("matched_keywords", [])
        if keywords:
            terms.append(" ".join(keywords[:3]))

        # 去重
        seen: set[str] = set()
        result = []
        for t in terms:
            if t.strip() and t.strip() not in seen:
                seen.add(t.strip())
                result.append(t.strip())

        return result

    # ==================================================================
    # Stage 4: Prompt 组装
    # ==================================================================

    def _assemble_rag_mode(
        self,
        existing_messages: List[Dict[str, str]],
        cleaned_input: str,
        knowledge_context: str,
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """严格 RAG 模式：回答必须 100% 来自知识库。

        调用前提：knowledge_context 非空（enrich_messages 中已判断）。
        """
        system_prompt = self.SYSTEM_BASE + "\n\n" + RAG_STRICT_SYSTEM_PROMPT

        analysis_context = self._build_analysis_context(log_analysis)
        if analysis_context:
            system_prompt += f"\n\n---\n## 补充：日志分析结果\n{analysis_context}"

        return [
            {"role": "system", "content": system_prompt},
        ] + [
            m for m in existing_messages if m.get("role") != "system"
        ] + [
            {
                "role": "user",
                "content": (
                    f"## 用户问题\n{cleaned_input}\n\n"
                    f"## 知识库检索结果（唯一事实来源）\n\n{knowledge_context}"
                ),
            },
        ]

    def _assemble_chat_mode(
        self,
        existing_messages: List[Dict[str, str]],
        cleaned_input: str,
        analysis: Dict[str, Any],
        log_analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """通用对话模式：自由对话（知识库无匹配时）。"""
        system_parts = [self.SYSTEM_BASE]

        analysis_context = self._build_analysis_context(log_analysis)
        if analysis_context:
            system_parts.append(f"\n## 日志分析结果\n\n{analysis_context}")

        if analysis.get("is_simple") and not log_analysis:
            system_parts.append(self.GUIDING_HINT)

        structured_user = self._structure_user_message(cleaned_input, analysis)

        enriched: List[Dict[str, str]] = [
            {"role": "system", "content": "\n".join(system_parts)},
        ]
        for m in existing_messages:
            if m.get("role") != "system":
                enriched.append(m)
        enriched.append({"role": "user", "content": structured_user})

        return enriched

    def _structure_user_message(
        self, text: str, analysis: Dict[str, Any],
    ) -> str:
        """将原始用户输入包装为结构化的 user message。

        绝不直接返回原始文本——始终附带处理上下文。
        """
        parts = [text]

        # 如果识别到子问题，明确列出
        sub_qs = analysis.get("sub_questions", [])
        if len(sub_qs) > 1:
            parts.append("\n\n[系统识别到以下子问题]")
            for i, sq in enumerate(sub_qs):
                parts.append(f"{i + 1}. {sq}")

        # 如果识别到关键词，提供上下文标签
        keywords = analysis.get("matched_keywords", [])
        if keywords:
            parts.append(f"\n[检测到诊断关键词: {', '.join(keywords[:5])}]")

        # 如果非诊断问题，提示 LLM 按通用对话处理
        if not analysis.get("is_diagnostic"):
            parts.append("\n[注意：此为通用问题，请以对话方式回复]")

        return "\n".join(parts)

    # ==================================================================
    # Fallback responses
    # ==================================================================

    def _build_refusal_response(
        self,
        existing_messages: List[Dict[str, str]],
        original: str,
    ) -> List[Dict[str, str]]:
        """构建拒绝响应——无害输入拒绝传递给 LLM。"""
        return [
            {"role": "system", "content": self.SYSTEM_BASE},
        ] + [
            m for m in existing_messages if m.get("role") != "system"
        ] + [
            {
                "role": "user",
                "content": (
                    f"[用户发送了无效输入，请友好地引导用户提出具体的诊断问题。"
                    f"原始输入已过滤: '{original[:20]}']"
                ),
            },
        ]

    # ==================================================================
    # Helpers
    # ==================================================================

    def _build_analysis_context(self, analysis: Optional[Dict[str, Any]]) -> str:
        """Format analysis results as context string."""
        if not analysis:
            return ""
        parts = []
        if analysis.get("summary"):
            parts.append(f"**诊断摘要**: {analysis['summary']}")
        if analysis.get("root_cause"):
            parts.append(f"**根因分析**: {analysis['root_cause']}")
        if analysis.get("confidence"):
            parts.append(f"**置信度**: {analysis['confidence']:.0%}")
        steps = analysis.get("next_steps", [])
        if steps:
            parts.append("**建议措施**:\n" + "\n".join(f"- {s}" for s in steps))
        return "\n".join(parts)
