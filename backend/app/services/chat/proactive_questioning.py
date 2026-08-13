"""主动追问系统（增强版） — 智能检测缺失信息并生成上下文自适应追问。

增强功能：
1. LLM 增强分析：调用 LLM 分析语义，智能判断缺失的关键信息
2. 上下文自适应：根据对话历史自适应调整追问策略
3. 多轮追踪：追踪追问轮次，避免重复追问
4. 用户画像：检测用户专业知识水平，调整追问难度
5. 追问优先级：按信息重要程度排序追问
6. 疲劳感知：检测用户是否有不耐烦迹象，适时停止追问
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class UserExpertiseLevel(str, Enum):
    """用户专业知识水平。"""
    NOVICE = "novice"       # 新手：需要引导式、通俗的追问
    INTERMEDIATE = "intermediate"  # 中级：可使用一定专业术语
    EXPERT = "expert"       # 专家：可使用技术术语，追问更精准


class QuestionPriority(int, Enum):
    """追问优先级。"""
    CRITICAL = 5  # 关键缺失（如故障现象）
    HIGH = 4      # 重要缺失（如设备型号）
    MEDIUM = 3    # 一般重要
    LOW = 2       # 辅助信息
    OPTIONAL = 1  # 可选信息


@dataclass
class QuestionItem:
    """单个追问条目。"""
    info_type: str          # 信息类别键
    category_name: str      # 类别名称（如 "设备型号"）
    priority: QuestionPriority
    questions: List[str]    # 可能的问法列表（按适配场景区分）
    is_critical: bool = False

    def get_question(self, expertise: UserExpertiseLevel) -> str:
        """根据用户水平选择合适的问法。"""
        if expertise == UserExpertiseLevel.NOVICE:
            # 更通俗、引导性的问法
            for q in self.questions:
                if "请" in q and len(q) < 50:
                    return q
        elif expertise == UserExpertiseLevel.EXPERT:
            # 更技术化、精准的问法
            for q in self.questions:
                if any(kw in q.lower() for kw in ["型号", "版本", "频率"]):
                    return q
        return self.questions[0] if self.questions else f"请提供{self.category_name}信息"


@dataclass
class QuestioningState:
    """追问状态追踪器。"""
    total_rounds: int = 0
    asked_info_types: Set[str] = field(default_factory=set)
    received_info_types: Set[str] = field(default_factory=set)
    user_refused_count: int = 0
    last_user_message_length: int = 0

    def record_asked(self, info_type: str) -> None:
        self.asked_info_types.add(info_type)
        self.total_rounds += 1

    def record_received(self, info_type: str) -> None:
        self.received_info_types.add(info_type)

    def was_already_asked(self, info_type: str) -> bool:
        return info_type in self.asked_info_types

    @property
    def should_stop_asking(self) -> bool:
        """判断是否应该停止追问。"""
        return (self.total_rounds >= 3 or
                self.user_refused_count >= 2)

    def reset(self) -> None:
        self.total_rounds = 0
        self.asked_info_types.clear()
        self.received_info_types.clear()
        self.user_refused_count = 0


class ProactiveQuestioning:
    """主动追问系统（增强版）。

    核心能力：
    1. 多维度缺失信息检测（关键词 + 语义分析 + LLM 增强）
    2. 上下文自适应追问生成
    3. 用户画像（专业知识水平）
    4. 追问状态追踪（避免重复、疲劳检测）
    """

    # ── 信息类别定义（带优先级和适配问法）─────────────────

    REQUIRED_INFO: Dict[str, Dict[str, Any]] = {
        "device_model": {
            "category_name": "设备型号",
            "priority": QuestionPriority.HIGH,
            "is_critical": True,
            "detection": {
                "keywords": ["设备", "机型", "型号", "model", "device", "产品"],
                "patterns": [
                    r"(?:设备|机型|型号|产品)[:：]?\s*([A-Z0-9\u4e00-\u9fff\-]+)",
                    r"model[:：]?\s*([A-Z0-9\-]+)",
                    r"(?:iPhone|小米|华为|OPPO|vivo|三星)[\s\dA-Za-z]*",
                ],
            },
            "questions": {
                UserExpertiseLevel.NOVICE: [
                    "请问您使用的是什么设备呢？（比如：iPhone 14、小米13等）",
                    "能告诉我您的设备型号吗？这样我能更准确地帮您分析",
                ],
                UserExpertiseLevel.INTERMEDIATE: [
                    "请问是什么设备型号？能否提供具体的型号和配置？",
                ],
                UserExpertiseLevel.EXPERT: [
                    "请提供设备型号及硬件配置信息",
                    "设备型号/SoC型号是什么？",
                ],
            },
        },
        "firmware_version": {
            "category_name": "固件/系统版本",
            "priority": QuestionPriority.MEDIUM,
            "is_critical": False,
            "detection": {
                "keywords": ["版本", "固件", "firmware", "version", "build", "系统"],
                "patterns": [
                    r"(?:版本|固件|系统|version)[:：]?\s*([\d.]+)",
                    r"build[:：]?\s*([A-Z0-9.]+)",
                    r"(?:Android|iOS|Windows)[\s\d.]+",
                ],
            },
            "questions": {
                UserExpertiseLevel.NOVICE: [
                    "请问设备当前的系统版本是多少？（在设置-关于里可以找到）",
                    "能帮我看看系统版本号吗？",
                ],
                UserExpertiseLevel.INTERMEDIATE: [
                    "请问设备当前的固件/系统版本是多少？",
                ],
                UserExpertiseLevel.EXPERT: [
                    "请提供固件版本号或 Build 号",
                ],
            },
        },
        "error_phenomenon": {
            "category_name": "故障现象",
            "priority": QuestionPriority.CRITICAL,
            "is_critical": True,
            "detection": {
                "keywords": [
                    "黑屏", "蓝屏", "死机", "重启", "卡死", "闪退",
                    "无法开机", "连不上", "无响应", "超时", "失败",
                    "花屏", "白屏", "重启循环", "bootloop",
                ],
                "patterns": [],
            },
            "questions": {
                UserExpertiseLevel.NOVICE: [
                    "能详细描述一下具体出现了什么异常吗？（比如：屏幕变黑了、自动重启了、还是连不上网了？）",
                    "设备出现了什么不正常的情况？可以具体描述一下吗？",
                ],
                UserExpertiseLevel.INTERMEDIATE: [
                    "请详细描述具体的故障现象（如：黑屏、重启、闪退等）",
                ],
                UserExpertiseLevel.EXPERT: [
                    "请描述故障现象和异常行为模式",
                    "能提供故障的具体表现和触发场景吗？",
                ],
            },
        },
        "error_frequency": {
            "category_name": "故障频率",
            "priority": QuestionPriority.MEDIUM,
            "is_critical": False,
            "detection": {
                "keywords": [
                    "偶尔", "经常", "总是", "一直", "频繁", "随机",
                    "sometimes", "always", "random", "frequent",
                    "每次", "间歇性",
                ],
                "patterns": [
                    r"(?:每|每隔)[\d一二三四五]+(?:次|天|小时|分钟)",
                    r"\d+%",
                ],
            },
            "questions": {
                UserExpertiseLevel.NOVICE: [
                    "这个问题是偶尔出现还是经常发生呢？",
                    "这个故障大概多久出现一次？",
                ],
                UserExpertiseLevel.INTERMEDIATE: [
                    "故障是间歇性还是持续性？发生的频率如何？",
                ],
                UserExpertiseLevel.EXPERT: [
                    "请描述故障的发生频率和概率",
                ],
            },
        },
        "reproduction_steps": {
            "category_name": "复现条件",
            "priority": QuestionPriority.HIGH,
            "is_critical": True,
            "detection": {
                "keywords": [
                    "步骤", "操作", "怎么", "如何", "复现", "重现",
                    "触发", "条件", "场景",
                ],
                "patterns": [
                    r"(?:当|在|触发|操作)[^。！？\n]{4,30}(?:时|后|之后)",
                ],
            },
            "questions": {
                UserExpertiseLevel.NOVICE: [
                    "请问是在做什么操作后出现这个问题的？可以描述一下当时的操作步骤吗？",
                    "您是在什么情况下发现这个问题的？",
                ],
                UserExpertiseLevel.INTERMEDIATE: [
                    "能否描述触发故障的操作步骤或场景？",
                ],
                UserExpertiseLevel.EXPERT: [
                    "请提供故障的复现步骤和触发条件",
                    "描述触发场景和最小复现步骤",
                ],
            },
        },
    }

    def __init__(self):
        self.state = QuestioningState()

    # ==================================================================
    # Public API
    # ==================================================================

    def analyze_missing_info(
        self,
        user_query: str,
        conversation_history: List[Dict[str, str]],
        detected_phenomenon: bool = False,
    ) -> List[QuestionItem]:
        """分析缺失的关键信息 — 支持 LLM 增强分析。

        Args:
            user_query: 当前用户问题
            conversation_history: 对话历史
            detected_phenomenon: 是否已检测到故障现象关键词

        Returns:
            缺失的信息条目列表（按优先级排序）
        """
        # 合并所有已出现过的文本
        all_text = self._build_all_text(user_query, conversation_history)

        missing_items: List[QuestionItem] = []

        for info_type, config in self.REQUIRED_INFO.items():
            # 检查是否已提供
            if self._is_info_provided(info_type, all_text, config["detection"]):
                self.state.record_received(info_type)
                continue

            # 检查是否已经追问过（避免重复）
            if self.state.was_already_asked(info_type):
                continue

            missing_items.append(QuestionItem(
                info_type=info_type,
                category_name=config["category_name"],
                priority=config["priority"],
                questions=self._get_question_variants(info_type, config),
                is_critical=config.get("is_critical", False),
            ))

        # 按优先级排序：CRITICAL > HIGH > MEDIUM > LOW
        missing_items.sort(key=lambda x: x.priority.value, reverse=True)
        return missing_items

    def should_ask_questions(
        self,
        user_query: str,
        conversation_history: List[Dict[str, str]],
        missing_info: Optional[List[QuestionItem]] = None,
    ) -> bool:
        """判断是否应该主动追问。

        决策因素：
        - 是否有至少一个 CRITICAL 级别的缺失信息
        - 对话轮次是否合理（≤3 轮追问）
        - 用户是否表现出拒绝倾向
        - 用户是否已有明确故障描述
        """
        # 检查是否应停止追问
        if self.state.should_stop_asking:
            return False

        # 检测用户拒绝信号
        if self._detect_user_refusal(user_query):
            self.state.user_refused_count += 1
            return False

        # 分析缺失信息
        if missing_info is None:
            missing_info = self.analyze_missing_info(user_query, conversation_history)

        # 至少有一个关键信息缺失才追问
        critical_missing = [item for item in missing_info if item.is_critical]
        has_error_phenomenon = self._has_error_phenomenon(user_query)

        # 如果用户已描述故障现象，降低追问门槛
        if has_error_phenomenon:
            return len(missing_info) >= 2

        return len(critical_missing) >= 1

    def generate_questions(
        self,
        missing_info: List[QuestionItem],
        user_expertise: Optional[UserExpertiseLevel] = None,
        max_questions: int = 3,
    ) -> List[str]:
        """生成追问问题列表。

        Args:
            missing_info: 缺失信息列表
            user_expertise: 用户专业知识水平
            max_questions: 最多追问数量

        Returns:
            追问问题文本列表
        """
        questions = []

        # 根据优先级排序
        sorted_items = sorted(missing_info, key=lambda x: x.priority.value, reverse=True)

        for item in sorted_items[:max_questions]:
            expertise = user_expertise or UserExpertiseLevel.INTERMEDIATE
            question = item.get_question(expertise)
            if question:
                questions.append(question)
                self.state.record_asked(item.info_type)

        return questions

    def format_proactive_response(
        self,
        questions: List[str],
        partial_answer: Optional[str] = None,
        user_expertise: Optional[UserExpertiseLevel] = None,
    ) -> str:
        """格式化主动追问的回复 — 根据用户水平调整语气。

        Args:
            questions: 追问问题列表
            partial_answer: 部分可提供的回答
            user_expertise: 用户水平

        Returns:
            格式化的追问回复
        """
        lines = []

        if partial_answer:
            lines.append(partial_answer)
            lines.append("")
            lines.append("---")
            lines.append("")

        expertise = user_expertise or UserExpertiseLevel.INTERMEDIATE

        # 根据用户水平调整引导语
        if expertise == UserExpertiseLevel.NOVICE:
            lines.append("为了更准确地帮您分析问题，我还想了解一下：")
        elif expertise == UserExpertiseLevel.EXPERT:
            lines.append("需要补充以下信息以精准定位根因：")
        else:
            lines.append("为了更准确地帮您诊断，我需要了解以下信息：")

        lines.append("")

        for i, question in enumerate(questions, 1):
            lines.append(f"{i}. {question}")

        lines.append("")
        if expertise == UserExpertiseLevel.NOVICE:
            lines.append("您提供这些信息后，我会帮您做更详细的分析~")
        else:
            lines.append("请提供这些信息后，我将为您进行更深入的分析。")

        return "\n".join(lines)

    # ==================================================================
    # LLM 增强分析
    # ==================================================================

    def analyze_with_llm(
        self,
        user_query: str,
        conversation_history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """使用 LLM 进行增强的缺失信息分析。

        Returns:
            {
                "missing_info_types": [...],  # 缺失的信息类别
                "user_expertise": "intermediate",
                "suggested_questions": [...],  # LLM 生成的追问
                "confidence": 0.85,
            }
        """
        try:
            from app.services.knowledge.provider_registry import ProviderRegistry

            provider = ProviderRegistry().get_provider("deepseek")
            prompt = self._build_llm_analysis_prompt(user_query, conversation_history)
            response = provider.chat([{"role": "user", "content": prompt}])
            return self._parse_llm_analysis_response(response)

        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "[ProactiveQuestioning] LLM analysis failed, fallback to keyword: %s", exc
            )
            return self._keyword_fallback_analysis(user_query, conversation_history)

    def _build_llm_analysis_prompt(
        self, user_query: str, history: List[Dict[str, str]],
    ) -> str:
        """构建 LLM 分析 prompt。"""
        history_text = "\n".join(
            f"{m['role']}: {m['content'][:200]}"
            for m in history[-6:]  # 最近 6 条消息
        )

        return f"""你是一个诊断信息完整性分析助手。请分析以下对话，判断用户是否提供了足够的诊断信息。

需要检测的信息类别：
1. device_model: 设备型号
2. firmware_version: 固件/系统版本
3. error_phenomenon: 故障现象（已描述 vs 未描述）
4. error_frequency: 故障频率
5. reproduction_steps: 复现条件/触发步骤

还需要判断：
- user_expertise: 用户专业知识水平 (novice/intermediate/expert)
- 是否有用户表现出不耐烦或拒绝追问的迹象

请以 JSON 格式返回：
{{
  "missing_info_types": ["device_model", "error_frequency"],
  "provided_info_types": ["error_phenomenon"],
  "user_expertise": "intermediate",
  "user_is_impatient": false,
  "suggested_questions": ["请问是什么设备型号？"],
  "analysis_summary": "用户描述了故障现象但缺少设备型号和故障频率"
}}

对话历史:
{history_text}

当前用户问题: {user_query}"""

    @staticmethod
    def _parse_llm_analysis_response(response: str) -> Dict[str, Any]:
        """解析 LLM 分析响应。"""
        import json

        response = response.strip()
        response = re.sub(r"^```(?:json)?\s*", "", response)
        response = re.sub(r"\s*```$", "", response)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 回退：基础解析
        return {
            "missing_info_types": [],
            "provided_info_types": [],
            "user_expertise": "intermediate",
            "user_is_impatient": False,
            "suggested_questions": [],
            "analysis_summary": "无法解析 LLM 响应",
        }

    def _keyword_fallback_analysis(
        self, user_query: str, history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """关键词回退分析。"""
        missing = self.analyze_missing_info(user_query, history)
        expertise = self._detect_user_expertise(history)

        return {
            "missing_info_types": [m.info_type for m in missing],
            "provided_info_types": list(self.state.received_info_types),
            "user_expertise": expertise.value,
            "user_is_impatient": self._detect_user_refusal(user_query),
            "suggested_questions": self.generate_questions(missing, expertise, 3),
            "analysis_summary": f"关键词分析: 缺失 {len(missing)} 项信息",
        }

    # ==================================================================
    # 用户画像
    # ==================================================================

    def _detect_user_expertise(
        self, conversation_history: List[Dict[str, str]],
    ) -> UserExpertiseLevel:
        """检测用户专业知识水平。

        评估维度：
        - 是否使用专业术语
        - 是否提供技术细节
        - 是否为简短描述
        """
        user_messages = [
            m["content"] for m in conversation_history
            if m.get("role") == "user"
        ]

        if not user_messages:
            return UserExpertiseLevel.INTERMEDIATE

        combined = " ".join(user_messages).lower()

        # 专业术语检测
        technical_terms = [
            "dmesg", "kernel", "firmware", "寄存器", "中断",
            "dma", "i2c", "spi", "uart", "phy", "pll",
            "soc", "dts", "device tree", "uboot", "bootloader",
            "mtp", "adb", "fastboot", "串口", "jtag",
        ]
        tech_score = sum(1 for t in technical_terms if t in combined)
        avg_msg_length = sum(len(m) for m in user_messages) / len(user_messages)

        if tech_score >= 3 and avg_msg_length > 50:
            return UserExpertiseLevel.EXPERT
        elif tech_score >= 1:
            return UserExpertiseLevel.INTERMEDIATE
        elif avg_msg_length < 15 and tech_score == 0:
            return UserExpertiseLevel.NOVICE

        return UserExpertiseLevel.INTERMEDIATE

    # ==================================================================
    # 拒绝检测
    # ==================================================================

    def _detect_user_refusal(self, user_query: str) -> bool:
        """检测用户是否表现出拒绝或不耐烦。"""
        refuse_keywords = [
            "不知道", "不清楚", "没有", "不记得", "don't know",
            "就这样", "你先分析", "别问了", "算了", "不用了",
        ]

        impatience_keywords = [
            "快点", "赶紧", "能不能直接", "别废话",
            "直接说", "不要说这些", "太麻烦了",
        ]

        query_lower = user_query.lower()

        if any(kw in query_lower for kw in refuse_keywords):
            return True

        if any(kw in query_lower for kw in impatience_keywords):
            return True

        return False

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _build_all_text(
        user_query: str, history: List[Dict[str, str]],
    ) -> str:
        """合并所有历史文本。"""
        parts = []
        for msg in history:
            if msg.get("role") == "user":
                parts.append(msg.get("content", ""))
        parts.append(user_query)
        return " ".join(parts)

    def _is_info_provided(
        self, info_type: str, all_text: str, detection: dict,
    ) -> bool:
        """检查某类信息是否已被用户提供。"""
        all_lower = all_text.lower()

        # 关键词检测：如果出现过相关关键词
        has_keywords = any(
            kw in all_lower for kw in detection.get("keywords", [])
        )

        # 模式检测：如果匹配到结构化信息（如型号、版本号）
        has_pattern = False
        for pattern in detection.get("patterns", []):
            if re.search(pattern, all_text, re.IGNORECASE):
                has_pattern = True
                break

        # 关键词匹配或结构化模式匹配任一满足即认为已提供
        # 对于"iPhone 14"这类不含中文"设备"关键词但匹配模式的情况，也应该识别
        return has_keywords or has_pattern

    def _get_question_variants(
        self, info_type: str, config: Dict[str, Any],
    ) -> List[str]:
        """获取某类信息的所有追问变体。"""
        all_variants = []
        questions = config.get("questions", {})
        for expertise_questions in questions.values():
            all_variants.extend(expertise_questions)
        return all_variants

    def _has_error_phenomenon(self, user_query: str) -> bool:
        """检查是否已包含故障现象描述。"""
        phenomenon_config = self.REQUIRED_INFO.get("error_phenomenon", {})
        keywords = phenomenon_config.get("detection", {}).get("keywords", [])
        return any(kw in user_query.lower() for kw in keywords)

    def reset_state(self) -> None:
        """重置追问状态。"""
        self.state.reset()


# ==================================================================
# 便捷函数：检查并生成追问
# ==================================================================

def check_and_generate_proactive_questions(
    user_query: str,
    conversation_history: List[Dict[str, str]],
    use_llm: bool = False,
) -> Optional[str]:
    """检查是否需要追问，如果需要则生成追问回复。

    Args:
        user_query: 当前用户问题
        conversation_history: 对话历史
        use_llm: 是否使用 LLM 增强分析

    Returns:
        如果需要追问，返回格式化的追问回复；否则返回 None
    """
    pq = ProactiveQuestioning()

    # 检测用户专业水平
    expertise = pq._detect_user_expertise(conversation_history)

    # 分析缺失信息
    missing_info = pq.analyze_missing_info(user_query, conversation_history)

    if not pq.should_ask_questions(user_query, conversation_history, missing_info):
        return None

    questions = pq.generate_questions(missing_info, expertise, max_questions=2)

    if not questions:
        return None

    return pq.format_proactive_response(questions, user_expertise=expertise)


def analyze_and_ask_with_llm(
    user_query: str,
    conversation_history: List[Dict[str, str]],
) -> Dict[str, Any]:
    """LLM 增强版本的追问分析 + 生成。

    Returns:
        {
            "should_ask": bool,
            "response": Optional[str],      # 追问回复文本
            "missing_info": List[str],       # 缺失信息类型
            "user_expertise": str,           # 用户水平
            "analysis_summary": str,         # 分析摘要
        }
    """
    pq = ProactiveQuestioning()

    result: Dict[str, Any] = {}

    def _run() -> None:
        try:
            result["analysis"] = pq.analyze_with_llm(
                user_query, conversation_history,
            )
        except Exception as exc:  # noqa: BLE001 - fallback below
            result["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(3.0)

    if thread.is_alive() or "analysis" not in result:
        analysis = pq._keyword_fallback_analysis(
            user_query, conversation_history,
        )
    else:
        analysis = result["analysis"]

    missing_types = analysis.get("missing_info_types", [])
    expertise = UserExpertiseLevel(analysis.get("user_expertise", "intermediate"))

    should_ask = (
        len(missing_types) > 0 and
        not analysis.get("user_is_impatient", False)
    )

    response = None
    if should_ask and analysis.get("suggested_questions"):
        response = pq.format_proactive_response(
            analysis["suggested_questions"],
            user_expertise=expertise,
        )

    return {
        "should_ask": should_ask,
        "response": response,
        "missing_info": missing_types,
        "user_expertise": expertise.value,
        "analysis_summary": analysis.get("analysis_summary", ""),
    }
