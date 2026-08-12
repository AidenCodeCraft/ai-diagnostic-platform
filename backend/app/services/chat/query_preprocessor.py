"""通用查询预处理模块 (QueryPreprocessor)

一劳永逸地解决知识库检索中"用户自然语言 → 有效搜索词"的转化问题。

=============================================================================
设计理念
=============================================================================

核心认知：用户的自然语言问题包含两种信息：
  A. 实体信息（名词）：设备型号、平台名、协议号 → 用于"定位文档"
  B. 意图信息（动词/现象）：统计、上线、录像、超速 → 用于"定位内容"

当前系统的问题在于：
  - 实体和意图混在一起搜索 → 搜索结果偏向实体但缺少意图匹配
  - 搜索词生成依赖硬编码规则 → 每个新场景都需要补规则
  - 搜索失败后没有降级重试机制 → 一次不匹配就直接放弃

本模块的解决思路：
  1. 通用分词：不依赖领域知识，纯粹从语言学角度分离实体词和意图词
  2. 分层搜索：先用实体定位文档，再用意图在文档内定位内容
  3. 降级策略：组合搜索 → 意图搜索 → 实体搜索，逐级降级
  4. 结果后验证：搜索结果返回后，做轻量级相关性校验再交给 LLM

=============================================================================
适用边界
=============================================================================

适用场景：
  - 用户用自然语言提问，问题中包含设备型号/平台名 + 功能/故障描述
  - 知识库文档标题/内容包含这些实体词和意图词
  - 向量搜索 + 关键词搜索混合模式

不适用场景：
  - 纯闲聊（由 _analyze_question 提前过滤）
  - 日志文件内容搜索（走 diagnosis_pipeline 独立管道）
  - Function Calling 模式（走 function_calling_agent 独立管道）

=============================================================================
核心流程
=============================================================================

用户输入: "L13C的客流统计是怎么样的呢？"

Step 1: 通用分词 (tokenize)
  → entities: ["L13C"]
  → intents:  ["客流", "统计"]
  → 完整中文段: ["客流统计"]

Step 2: 搜索策略生成 (build_search_plan)
  → 第1层（组合搜索）: ["L13C 客流统计", "L13C 客流"]
  → 第2层（意图搜索）: ["客流统计", "客流", "统计"]
  → 第3层（实体搜索）: ["L13C"]

Step 3: 执行搜索 (execute_search)
  → 第1层搜索 → 有高分结果(≥0.3) → 直接返回
  → 第1层无结果 → 第2层搜索 → 有结果 → 返回
  → 第2层无结果 → 第3层搜索 → 返回

Step 4: 结果校验 (validate_results)
  → 检查返回的文档内容是否至少包含一个意图词
  → 如果不包含 → 标记为"部分匹配"或"无匹配"

=============================================================================
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# =========================================================================
# 通用停用词 — 纯语言学角度，不依赖任何领域知识
# =========================================================================

# 疑问/语气词
_QUESTION_WORDS: Set[str] = {
    "什么", "怎么", "为什么", "怎么样", "如何", "哪", "哪些",
    "呢", "吗", "吧", "啊", "呀", "哦", "嗯", "哈",
    "是什么", "是怎么", "是怎样的", "是怎么样的", "是什么样的",
    "什么样", "怎样的",
}

# 结构虚词（连接词、介词、代词等）
_STRUCTURE_WORDS: Set[str] = {
    "的", "了", "在", "是", "我", "你", "他", "她", "它",
    "们", "有", "和", "与", "或", "就", "也", "都", "还",
    "要", "会", "能", "可以", "应该", "需要", "必须",
    "这", "那", "这个", "那个", "这些", "那些",
    "一个", "一下", "一些", "一种",
    "进行", "使用", "通过", "根据", "关于", "对于",
    "之中", "之内", "之外", "之间",
}

# 指令性短语
_INSTRUCTION_PHRASES: Set[str] = {
    "帮我", "帮我搜", "帮我搜索", "帮我查", "帮我查找",
    "请帮我", "请搜索", "请查找", "请检索",
    "搜索一下", "查一下", "搜一下", "找一下",
    "我想知道", "我想了解", "我想问", "请问",
    "搜一下知识库", "查找知识库", "搜索知识库",
    "知识库里面", "知识库中",
}

# 无意义短词（分词产生的碎片）
_NOISE_TOKENS: Set[str] = {
    "的客", "的流", "是怎", "么样", "计是", "流统",
    "中搜", "志中", "在日", "该在", "我应",
}

# =========================================================================
# 数据结构
# =========================================================================


@dataclass
class TokenizedQuery:
    """分词结果"""
    raw: str                          # 原始输入
    entities: List[str]               # 实体词：型号、协议号、平台名等（字母数字 + 中文专有名词）
    intents: List[str]                # 意图词：功能描述、故障现象等（纯中文关键词）
    full_segments: List[str]          # 完整中文段（分割后的纯中文段，2-6字）
    cleaned: str                      # 剥离指令后的完整问题


@dataclass
class SearchPlan:
    """搜索计划"""
    layers: List[SearchLayer]         # 分层搜索策略
    fallback_terms: List[str] = field(default_factory=list)  # 最终兜底词


@dataclass
class SearchLayer:
    """搜索层"""
    priority: int                     # 优先级（越小越优先）
    name: str                         # 层名称（用于日志）
    terms: List[str]                  # 搜索词列表
    stop_on_high_score: bool = True   # 找到高分结果是否停止
    page_size: int = 5                # 每页结果数


@dataclass
class SearchResult:
    """搜索结果"""
    items: List[Dict[str, Any]]
    matched_layer: str                # 匹配到的搜索层
    matched_term: str                 # 匹配到的搜索词
    total_attempted: int              # 总共尝试的搜索词数
    is_partial_match: bool = False    # 是否部分匹配（实体匹配但意图不匹配）


# =========================================================================
# QueryPreprocessor 核心类
# =========================================================================


class QueryPreprocessor:
    """通用查询预处理器。

    使用方法：
        preprocessor = QueryPreprocessor()
        result = preprocessor.process(
            query="L13C的客流统计是怎么样的呢？",
            search_fn=lambda term, size: knowledge.search(term, page=1, page_size=size),
        )
        # result.items → 搜索结果列表
        # result.matched_layer → 匹配到的搜索层
        # result.is_partial_match → 是否需要 LLM 特殊处理
    """

    # 中文专有名词模式：以常见后缀结尾的2-6字中文词
    _PROPER_NOUN_PATTERN = re.compile(
        r'[\u4e00-\u9fff]{2,6}(?:平台|系统|设备|模块|服务|终端|服务器|客户端)'
    )

    # 中文实体后缀（可剥离以生成简称变体）
    _ENTITY_SUFFIXES = [
        "平台", "系统", "设备", "模块", "服务", "终端",
        "服务器", "客户端", "管理端", "网关", "控制器",
        "传感器", "摄像头", "录像机", "采集器",
    ]

    # 中文实体前缀（可剥离以生成核心词变体）
    _ENTITY_PREFIXES = [
        "基于", "面向", "针对", "用于", "支持",
    ]

    # 字母数字组合（设备型号、协议号等）
    _ALPHANUM_PATTERN = re.compile(r'[A-Za-z]*\d+[A-Za-z]*')

    # 非中文分割符：字母、数字、标点、虚词
    _CN_SEPARATOR_PATTERN = re.compile(
        r'[a-zA-Z0-9\s，,。.？?！!：:；;、'
        r'的之与和或是什么怎么如何哪哪些呢吗吧啊呀哦嗯哈'
        r'了我你他她它们有也都要会能可以应该需要必须'
        r'这那进行使用通过根据关于对于'
        r']+'
    )

    # 指令剥离正则
    _INSTRUCTION_STRIP_PATTERNS = [
        re.compile(r'^(?:请)?(?:帮我)?(?:搜(?:一下|索)?|查找|检索|查一下|搜一下)(?:知识库|资料|文档)?(?:里面|中)?(?:的)?(?:内容|信息|资料)?[，,。.\s]*'),
        re.compile(r'^(?:我想知道|我想了解|我想问|请问)[，,。.\s]*'),
        re.compile(r'^(?:关于|有关)[，,。.\s]*'),
    ]
    _INSTRUCTION_SUFFIX_PATTERNS = [
        re.compile(r'[，,。.\s]*(?:的内容|的信息|的资料|相关(?:内容|信息|资料))(?:[吗呢吧]?[？?！!]*)?$'),
    ]

    # 日志长度阈值
    _LOG_LONG_THRESHOLD = 200  # 超过此长度视为日志内容
    _LOG_KEYWORD_PATTERNS = [
        re.compile(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'),  # 时间戳
        re.compile(r'\[(?:ERROR|WARN|INFO|DEBUG|FATAL)\]'),     # 日志级别
        re.compile(r'at\s+\S+\.\S+:\d+'),                       # 堆栈跟踪
    ]

    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # 实体变体生成：全称 → 简称 / 简称 → 全称
    # ------------------------------------------------------------------

    @staticmethod
    def generate_entity_variants(entity: str) -> List[str]:
        """为中文实体词生成搜索变体。

        策略：
          1. 剥离常见后缀生成简称（如"启迪云控平台" → "启迪云控"）
          2. 剥离常见前缀生成核心词
          3. 保留原始实体作为精确匹配项

        示例：
          "启迪云控平台" → ["启迪云控平台", "启迪云控"]
          "L13C设备"     → ["L13C设备", "L13C"]
          "客流统计模块" → ["客流统计模块", "客流统计"]
          "超速报警系统" → ["超速报警系统", "超速报警"]
        """
        variants: List[str] = [entity]  # 保留原始形式

        # 1. 剥离后缀
        for suffix in QueryPreprocessor._ENTITY_SUFFIXES:
            if entity.endswith(suffix) and len(entity) > len(suffix):
                stripped = entity[:-len(suffix)]
                if len(stripped) >= 2 and stripped not in variants:
                    variants.append(stripped)
                break  # 只剥离一个后缀

        # 2. 剥离前缀
        for prefix in QueryPreprocessor._ENTITY_PREFIXES:
            if entity.startswith(prefix) and len(entity) > len(prefix):
                stripped = entity[len(prefix):]
                if len(stripped) >= 2 and stripped not in variants:
                    variants.append(stripped)
                break  # 只剥离一个前缀

        # 3. 同时剥离前缀和后缀（如果都有）
        if len(variants) >= 2:
            # 如果原始实体有前缀和后缀，生成双重剥离版本
            core = variants[-1]  # 取上一步的结果
            for suffix in QueryPreprocessor._ENTITY_SUFFIXES:
                if core.endswith(suffix) and len(core) > len(suffix):
                    stripped = core[:-len(suffix)]
                    if len(stripped) >= 2 and stripped not in variants:
                        variants.append(stripped)
                    break

        return variants

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------

    def process(
        self,
        query: str,
        search_fn: callable,
        *,
        max_layers: int = 4,
        high_score_threshold: float = 0.3,
        min_intent_match_ratio: float = 0.3,
    ) -> SearchResult:
        """完整的预处理 → 搜索 → 校验流程。

        Args:
            query: 用户原始输入
            search_fn: 搜索函数，签名为 (term: str, page_size: int) -> dict
                       返回格式: {"items": [{"id": ..., "title": ..., "relevance_score": ..., ...}]}
            max_layers: 最大搜索层数
            high_score_threshold: 高分阈值，达到此分数视为高质量匹配
            min_intent_match_ratio: 最低意图词匹配比例，低于此值视为部分匹配

        Returns:
            SearchResult: 包含搜索结果和匹配信息
        """
        # Step 1: 分词
        tokenized = self.tokenize(query)
        logger.info(
            "[QueryPreprocessor] 分词结果: entities=%s, intents=%s, segments=%s",
            tokenized.entities, tokenized.intents, tokenized.full_segments,
        )

        # Step 2: 生成搜索计划
        plan = self.build_search_plan(tokenized, max_layers=max_layers)
        logger.info(
            "[QueryPreprocessor] 搜索计划: %s",
            [(l.priority, l.name, l.terms[:5]) for l in plan.layers],
        )

        # Step 3: 执行搜索
        result = self._execute_plan(plan, search_fn, high_score_threshold)

        # Step 4: 结果校验
        if result.items:
            result.is_partial_match = self._check_partial_match(
                result.items, tokenized.intents, min_intent_match_ratio,
            )
            if result.is_partial_match:
                logger.info("[QueryPreprocessor] 部分匹配：实体匹配但意图不匹配")

        logger.info(
            "[QueryPreprocessor] 搜索完成: layer=%s, term=%s, items=%d, partial=%s",
            result.matched_layer, result.matched_term,
            len(result.items), result.is_partial_match,
        )
        return result

    # ------------------------------------------------------------------
    # Step 1: 通用分词
    # ------------------------------------------------------------------

    def tokenize(self, query: str) -> TokenizedQuery:
        """将自然语言问题分解为实体词和意图词。

        策略：
        1. 字母数字 → 实体词（设备型号、协议号）
        2. 中文专有名词模式 → 实体词（"X平台"、"X系统"）
        3. 剩余纯中文段 → 意图词
        4. 剥离指令前缀/后缀
        """
        raw = query.strip()

        # 1. 提取字母数字实体
        entities: List[str] = []
        for match in self._ALPHANUM_PATTERN.finditer(raw):
            token = match.group()
            if len(token) >= 2:
                entities.append(token)

        # 2. 提取中文专有名词实体
        for match in self._PROPER_NOUN_PATTERN.finditer(raw):
            token = match.group()
            if token not in entities:
                entities.append(token)

        # 3. 分割中文段
        segments = self._CN_SEPARATOR_PATTERN.split(raw)
        segments = [s.strip() for s in segments if len(s.strip()) >= 2]

        # 4. 从中文段中提取意图词
        intents: List[str] = []
        full_segments: List[str] = []
        for seg in segments:
            if len(seg) <= 6:
                # 短段：直接作为完整中文段
                if seg not in entities:
                    full_segments.append(seg)
            else:
                # 长段：提取有意义的 3-4 字片段（非碎片）
                # 策略：只取开头和结尾各 2 个片段，避免中间碎片
                for start in [0, 1, 2]:
                    for w in [3, 4]:
                        if start + w <= len(seg):
                            sub = seg[start:start + w]
                            # 过滤纯碎片（包含无意义短字的跳过）
                            if sub not in full_segments and sub not in entities:
                                full_segments.append(sub)
                # 尾部：取最后 3-4 个字
                for offset in [3, 4, 5]:
                    start = len(seg) - offset
                    for w in [3, 4]:
                        if start >= 0 and start + w <= len(seg):
                            sub = seg[start:start + w]
                            if sub not in full_segments and sub not in entities:
                                full_segments.append(sub)

            # 从段中提取意图词（2-4字）
            for i in range(len(seg) - 1):
                for w in [2, 3, 4]:
                    if i + w <= len(seg):
                        phrase = seg[i:i + w]
                        if phrase not in intents:
                            intents.append(phrase)

        # 5. 过滤停用词和碎片
        all_stop = _QUESTION_WORDS | _STRUCTURE_WORDS | _NOISE_TOKENS
        intents = [w for w in intents if w not in all_stop and w not in entities]
        # full_segments 额外过滤：去掉被其他更长 segment 包含的短片段
        full_segments = [s for s in full_segments if s not in all_stop and s not in entities]
        # 去重：如果短片段是长片段的子串，保留长片段
        filtered_segments: List[str] = []
        for seg in sorted(full_segments, key=len, reverse=True):
            if not any(seg in other and seg != other for other in filtered_segments):
                filtered_segments.append(seg)
        full_segments = filtered_segments

        # 6. 剥离指令 → cleaned
        cleaned = raw
        for pat in self._INSTRUCTION_STRIP_PATTERNS:
            cleaned = pat.sub("", cleaned, count=1)
        for pat in self._INSTRUCTION_SUFFIX_PATTERNS:
            cleaned = pat.sub("", cleaned)
        cleaned = cleaned.strip()

        return TokenizedQuery(
            raw=raw,
            entities=entities,
            intents=intents,
            full_segments=full_segments,
            cleaned=cleaned,
        )

    # ------------------------------------------------------------------
    # Step 2: 搜索计划生成
    # ------------------------------------------------------------------

    def build_search_plan(
        self, tokenized: TokenizedQuery, max_layers: int = 4,
    ) -> SearchPlan:
        """生成分层搜索计划。

        层次结构：
          Layer 1 (组合搜索):   实体变体 + 完整中文段 → 最精确
          Layer 2 (实体变体):   实体变体单独搜索（简称/全称）→ 精确定位文档
          Layer 3 (意图搜索):   完整中文段 + 意图词 → 内容匹配
          Layer 4 (实体搜索):   原始实体词 → 兜底
        """
        layers: List[SearchLayer] = []
        priority = 1

        entities = tokenized.entities
        intents = tokenized.intents
        segments = tokenized.full_segments

        # ── 生成实体变体 ──
        # 对每个中文实体（带后缀的），生成剥离后缀的简称
        entity_variants: List[str] = []
        for ent in entities:
            variants = self.generate_entity_variants(ent)
            for v in variants:
                if v not in entity_variants:
                    entity_variants.append(v)

        # 用于组合搜索的实体列表（包含变体）
        all_entity_terms = list(dict.fromkeys(entity_variants + entities))

        # Layer 1: 组合搜索（实体变体 + 中文段）
        if all_entity_terms and segments and priority <= max_layers:
            combo_terms: List[str] = []
            for ent in all_entity_terms[:4]:
                for seg in segments[:3]:
                    combo = f"{ent} {seg}"
                    if combo not in combo_terms:
                        combo_terms.append(combo)
                    no_space = f"{ent}{seg}"
                    if no_space not in combo_terms:
                        combo_terms.append(no_space)
            if combo_terms:
                layers.append(SearchLayer(
                    priority=priority, name="组合搜索",
                    terms=combo_terms, page_size=5,
                ))
                priority += 1

        # Layer 2: 实体变体搜索（简称优先，因为文档中通常用简称）
        # 例："启迪云控平台" → 先搜"启迪云控"（简称），再搜"启迪云控平台"（全称）
        if entity_variants and priority <= max_layers:
            # 简称（剥离后缀的）优先
            variant_terms: List[str] = []
            for v in entity_variants:
                if v not in variant_terms:
                    variant_terms.append(v)
            # 加上原始实体（如果不在列表中）
            for ent in entities:
                if ent not in variant_terms:
                    variant_terms.append(ent)
            if variant_terms:
                layers.append(SearchLayer(
                    priority=priority, name="实体变体",
                    terms=variant_terms[:8], page_size=5,
                    stop_on_high_score=True,
                ))
                priority += 1

        # Layer 3: 意图搜索（中文段 + 意图词）
        if (segments or intents) and priority <= max_layers:
            intent_terms: List[str] = []
            # 完整中文段优先（如 "客流统计" 优于 "客流" + "统计"）
            for seg in segments[:5]:
                if seg not in intent_terms:
                    intent_terms.append(seg)
            # 然后子词拆分（4字 → 2字+2字）
            for seg in segments:
                if len(seg) == 4:
                    left, right = seg[:2], seg[2:]
                    for sub in [left, right]:
                        if sub not in intent_terms and len(sub) >= 2:
                            intent_terms.append(sub)
            # 最后其他意图词
            for w in intents:
                if w not in intent_terms and len(w) <= 4:
                    intent_terms.append(w)
            if intent_terms:
                layers.append(SearchLayer(
                    priority=priority, name="意图搜索",
                    terms=intent_terms[:15], page_size=5,
                ))
                priority += 1

        # Layer 4: 实体搜索（原始实体词兜底）
        if entities and priority <= max_layers:
            layers.append(SearchLayer(
                priority=priority, name="实体搜索",
                terms=entities[:5], page_size=3,
            ))
            priority += 1

        # 兜底：完整 cleaned query
        fallback_terms: List[str] = []
        cleaned = tokenized.cleaned
        if cleaned and len(cleaned) >= 2:
            fallback_terms.append(cleaned)

        return SearchPlan(layers=layers, fallback_terms=fallback_terms)

    # ------------------------------------------------------------------
    # Step 3: 执行搜索
    # ------------------------------------------------------------------

    def _execute_plan(
        self,
        plan: SearchPlan,
        search_fn: callable,
        high_score_threshold: float = 0.3,
    ) -> SearchResult:
        """按分层计划执行搜索，逐层降级。"""
        all_items: List[Dict[str, Any]] = []
        seen_ids: Set[int] = set()
        high_score_ids: Set[int] = set()
        matched_layer = "无匹配"
        matched_term = ""
        total_attempted = 0

        # 按层执行
        for layer in plan.layers:
            layer_has_result = False

            for term in layer.terms:
                total_attempted += 1
                try:
                    result = search_fn(term, layer.page_size)
                    items = result.get("items", []) if isinstance(result, dict) else []
                except Exception as e:
                    logger.warning("[QueryPreprocessor] 搜索失败: term=%s, error=%s", term, e)
                    continue

                for item in items:
                    doc_id = item.get("id")
                    score = float(item.get("relevance_score", 0) or 0)

                    if score >= high_score_threshold:
                        high_score_ids.add(doc_id)

                    if doc_id in seen_ids:
                        # 更新已有结果的最高分
                        for existing in all_items:
                            if existing.get("id") == doc_id:
                                if score > float(existing.get("relevance_score", 0) or 0):
                                    existing["relevance_score"] = score
                                break
                        continue

                    seen_ids.add(doc_id)
                    all_items.append(item)
                    layer_has_result = True

                if layer_has_result:
                    matched_layer = layer.name
                    matched_term = term

                # 找到高分结果且该层允许提前停止
                if layer.stop_on_high_score and high_score_ids and len(all_items) >= 3:
                    break

            # 如果该层找到了高分结果，停止降级
            if high_score_ids and len(all_items) >= 3:
                break

        # 兜底：用 fallback 词搜索
        if not all_items and plan.fallback_terms:
            for term in plan.fallback_terms[:3]:
                total_attempted += 1
                try:
                    result = search_fn(term, 3)
                    items = result.get("items", []) if isinstance(result, dict) else []
                except Exception:
                    continue
                for item in items:
                    doc_id = item.get("id")
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        all_items.append(item)
                if all_items:
                    matched_layer = "兜底搜索"
                    matched_term = term
                    break

        # 排序
        all_items.sort(
            key=lambda d: float(d.get("relevance_score", 0) or 0),
            reverse=True,
        )

        return SearchResult(
            items=all_items[:8],
            matched_layer=matched_layer,
            matched_term=matched_term,
            total_attempted=total_attempted,
        )

    # ------------------------------------------------------------------
    # Step 4: 结果校验
    # ------------------------------------------------------------------

    def _check_partial_match(
        self,
        items: List[Dict[str, Any]],
        intents: List[str],
        min_ratio: float = 0.3,
    ) -> bool:
        """检查搜索结果是否仅为部分匹配。

        判断标准：返回的文档内容中，意图词的匹配比例。
        如果意图词匹配比例过低（< min_ratio），说明找到了实体相关的文档
        但内容与用户意图不符，需要 LLM 做特殊处理（如分区输出）。
        """
        if not intents:
            return False

        # 合并所有文档的 title + content
        all_text_parts: List[str] = []
        for item in items[:5]:
            title = item.get("title", "")
            content = item.get("content", "") or item.get("snippet", "")
            all_text_parts.append(f"{title} {content}")
        combined_text = " ".join(all_text_parts).lower()

        # 统计意图词命中数
        matched = 0
        for intent in intents[:10]:
            if intent.lower() in combined_text:
                matched += 1

        ratio = matched / min(len(intents), 10) if intents else 1.0
        return ratio < min_ratio

    # ------------------------------------------------------------------
    # 工具方法：判断输入是否为日志内容
    # ------------------------------------------------------------------

    def is_log_content(self, text: str) -> bool:
        """判断输入是否为日志内容（而非自然语言问题）。"""
        if len(text) < self._LOG_LONG_THRESHOLD:
            return False
        for pattern in self._LOG_KEYWORD_PATTERNS:
            if pattern.search(text):
                return True
        return False


# =========================================================================
# 工厂函数：便捷使用
# =========================================================================

# 全局单例
_preprocessor: Optional[QueryPreprocessor] = None


def get_preprocessor() -> QueryPreprocessor:
    """获取全局预处理器实例。"""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = QueryPreprocessor()
    return _preprocessor


def preprocess_and_search(
    query: str,
    search_fn: callable,
    **kwargs,
) -> SearchResult:
    """便捷函数：一步完成预处理和搜索。

    Args:
        query: 用户原始输入
        search_fn: 搜索函数 (term, page_size) -> dict
        **kwargs: 传递给 QueryPreprocessor.process() 的其他参数

    Returns:
        SearchResult
    """
    return get_preprocessor().process(query, search_fn, **kwargs)
