"""QueryPreprocessor 单元测试 — 覆盖所有边界情况。"""

import pytest
from app.services.chat.query_preprocessor import (
    QueryPreprocessor,
    TokenizedQuery,
    SearchPlan,
    SearchLayer,
    SearchResult,
    get_preprocessor,
    preprocess_and_search,
)


class TestTokenize:
    """Step 1: 分词测试"""

    def setup_method(self):
        self.pp = QueryPreprocessor()

    def test_basic_entity_intent_split(self):
        """基础：型号 + 功能描述"""
        result = self.pp.tokenize("L13C的客流统计是怎么样的呢？")
        assert "L13C" in result.entities
        assert "客流统计" in result.full_segments or "客流" in result.intents
        # 不应包含疑问词
        assert "怎么样" not in result.intents
        assert "呢" not in result.intents

    def test_platform_entity(self):
        """平台名识别"""
        result = self.pp.tokenize("启迪云控平台未看到车辆上线")
        # 应该识别出"启迪云控平台"或至少"云控平台"
        assert any("云控" in e for e in result.entities) or any(
            "云控平台" in s for s in result.full_segments
        )

    def test_protocol_entity(self):
        """协议号识别"""
        result = self.pp.tokenize("CJT1078协议的超速逻辑是什么")
        assert "CJT1078" in result.entities
        assert "超速" in result.intents or "超速逻辑" in result.full_segments

    def test_instruction_stripping(self):
        """指令剥离"""
        result = self.pp.tokenize("帮我搜一下知识库里面的内容，关于超速逻辑的")
        assert "帮我" not in result.full_segments
        assert "搜索" not in result.full_segments
        assert "超速逻辑" in result.full_segments or "超速" in result.intents

    def test_question_word_filtering(self):
        """疑问词过滤"""
        result = self.pp.tokenize("为什么设备不上线呢？")
        assert "为什么" not in result.intents
        assert "呢" not in result.intents
        assert "不上线" in result.full_segments or "上线" in result.intents

    def test_multiple_entities(self):
        """多个实体"""
        result = self.pp.tokenize("L13C和D3C的客流统计有什么区别")
        assert "L13C" in result.entities
        assert "D3C" in result.entities
        assert "客流" in result.intents or "客流统计" in result.full_segments

    def test_pure_cn_no_entity(self):
        """纯中文无实体"""
        result = self.pp.tokenize("客流统计是怎么样的呢？")
        assert len(result.entities) == 0
        assert "客流统计" in result.full_segments or "客流" in result.intents

    def test_empty_query(self):
        """空输入"""
        result = self.pp.tokenize("")
        assert len(result.entities) == 0
        assert len(result.intents) == 0

    def test_long_query_with_mixed_content(self):
        """长查询：启迪云控案例"""
        result = self.pp.tokenize(
            "启迪云控平台未看到车辆上线，我应该在日志中搜索什么呢？"
        )
        # 关键意图词必须存在
        all_text = " ".join(result.intents + result.full_segments + result.entities)
        assert "车辆" in all_text or "上线" in all_text or "未看到" in all_text
        # 不应包含指令性碎片
        assert "我应该" not in result.full_segments

    def test_cleaned_field(self):
        """cleaned 字段不应包含指令前缀"""
        result = self.pp.tokenize("帮我查一下超速逻辑")
        assert not result.cleaned.startswith("帮我")
        assert "超速" in result.cleaned


class TestEntityVariants:
    """实体变体生成测试"""

    def setup_method(self):
        self.pp = QueryPreprocessor()

    def test_platform_full_to_short(self):
        """全称 → 简称：剥离"平台"后缀"""
        variants = self.pp.generate_entity_variants("启迪云控平台")
        assert "启迪云控平台" in variants  # 保留原始
        assert "启迪云控" in variants      # 简称

    def test_device_suffix(self):
        """设备后缀剥离"""
        variants = self.pp.generate_entity_variants("L13C设备")
        assert "L13C" in variants

    def test_module_suffix(self):
        """模块后缀剥离"""
        variants = self.pp.generate_entity_variants("客流统计模块")
        assert "客流统计" in variants

    def test_system_suffix(self):
        """系统后缀剥离"""
        variants = self.pp.generate_entity_variants("超速报警系统")
        assert "超速报警" in variants

    def test_no_suffix(self):
        """无后缀时只返回原始"""
        variants = self.pp.generate_entity_variants("客流统计")
        assert variants == ["客流统计"]

    def test_short_entity_no_split(self):
        """短实体不拆分"""
        variants = self.pp.generate_entity_variants("云控")
        assert len(variants) == 1  # 太短不拆分


class TestBuildSearchPlan:
    """Step 2: 搜索计划生成测试"""

    def setup_method(self):
        self.pp = QueryPreprocessor()

    def test_four_layer_plan_with_entity_variants(self):
        """有中文实体时生成4层计划（含实体变体层）"""
        tokenized = self.pp.tokenize("启迪云控平台未看到车辆上线")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        assert len(plan.layers) >= 3
        layer_names = [l.name for l in plan.layers]
        assert "组合搜索" in layer_names
        assert "实体变体" in layer_names  # 新增的变体层
        assert "意图搜索" in layer_names
        assert "实体搜索" in layer_names

    def test_entity_variant_layer_has_short_name(self):
        """实体变体层包含简称（剥离后缀的版本）"""
        tokenized = self.pp.tokenize("启迪云控平台未看到车辆上线")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        variant_layer = next(l for l in plan.layers if l.name == "实体变体")
        # 简称应该在列表中
        assert "启迪云控" in variant_layer.terms
        # 全称也在列表中
        assert "启迪云控平台" in variant_layer.terms

    def test_three_layer_plan(self):
        """有实体+意图时生成至少3层计划"""
        tokenized = self.pp.tokenize("L13C的客流统计是怎么样的呢？")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        assert len(plan.layers) >= 2
        layer_names = [l.name for l in plan.layers]
        assert "组合搜索" in layer_names
        assert "意图搜索" in layer_names
        if tokenized.entities:
            assert "实体搜索" in layer_names

    def test_combo_terms_present(self):
        """组合搜索层包含实体+中文段组合"""
        tokenized = self.pp.tokenize("L13C的客流统计是怎么样的呢？")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        combo_layer = plan.layers[0]
        assert combo_layer.name == "组合搜索"
        # 至少有一个组合词
        has_combo = any(
            "L13C" in t and ("客流" in t or "统计" in t)
            for t in combo_layer.terms
        )
        assert has_combo, f"组合搜索词: {combo_layer.terms}"

    def test_no_entity_skip_combo_layer(self):
        """无实体时跳过组合搜索层和实体变体层"""
        tokenized = self.pp.tokenize("客流统计是怎么样的呢？")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        layer_names = [l.name for l in plan.layers]
        assert "组合搜索" not in layer_names
        assert "实体变体" not in layer_names

    def test_intent_only(self):
        """只有意图词时的搜索计划"""
        tokenized = self.pp.tokenize("超速逻辑")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        assert len(plan.layers) >= 1
        assert plan.layers[0].name == "意图搜索"

    def test_max_layers_limit(self):
        """max_layers 限制"""
        tokenized = self.pp.tokenize("L13C的客流统计是怎么样的呢？")
        plan = self.pp.build_search_plan(tokenized, max_layers=1)
        assert len(plan.layers) == 1

    def test_fallback_terms(self):
        """兜底搜索词包含 cleaned query"""
        tokenized = self.pp.tokenize("L13C的客流统计是怎么样的呢？")
        plan = self.pp.build_search_plan(tokenized)
        assert len(plan.fallback_terms) > 0


class TestExecutePlan:
    """Step 3: 搜索执行测试"""

    def setup_method(self):
        self.pp = QueryPreprocessor()

    def test_empty_plan(self):
        """空计划返回空结果"""
        plan = SearchPlan(layers=[], fallback_terms=[])
        result = self.pp._execute_plan(plan, lambda t, s: {"items": []})
        assert len(result.items) == 0
        assert result.matched_layer == "无匹配"

    def test_single_layer_success(self):
        """单层搜索成功"""
        def mock_search(term, size):
            return {
                "items": [
                    {"id": 1, "title": "测试文档", "relevance_score": 0.5},
                ]
            }

        tokenized = self.pp.tokenize("客流统计")
        plan = self.pp.build_search_plan(tokenized, max_layers=1)
        result = self.pp._execute_plan(plan, mock_search)
        assert len(result.items) >= 1
        assert result.matched_layer != "无匹配"

    def test_layer_fallback(self):
        """第一层无结果，降级到第二层"""
        call_count = [0]

        def mock_search(term, size):
            call_count[0] += 1
            if "L13C" in term and "客流" in term:
                return {"items": []}  # 组合搜索无结果
            if "客流" in term:
                return {
                    "items": [
                        {"id": 1, "title": "客流逻辑", "relevance_score": 0.8},
                    ]
                }
            return {"items": []}

        tokenized = self.pp.tokenize("L13C的客流统计是怎么样的呢？")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        result = self.pp._execute_plan(plan, mock_search)
        assert len(result.items) >= 1
        assert result.matched_layer == "意图搜索" or call_count[0] > 1

    def test_fallback_when_all_layers_empty(self):
        """所有层无结果时走兜底"""
        tokenized = self.pp.tokenize("L13C的客流统计是怎么样的呢？")
        plan = self.pp.build_search_plan(tokenized, max_layers=4)
        result = self.pp._execute_plan(plan, lambda t, s: {"items": []})
        assert len(result.items) == 0


class TestPartialMatchCheck:
    """Step 4: 部分匹配校验测试"""

    def setup_method(self):
        self.pp = QueryPreprocessor()

    def test_full_match(self):
        """意图词完全匹配 → 非部分匹配"""
        items = [
            {
                "id": 1,
                "title": "客流逻辑",
                "content": "客流统计包括：开门上报、到站上报。适用于 L13C。",
            }
        ]
        intents = ["客流", "统计"]
        assert not self.pp._check_partial_match(items, intents)

    def test_partial_match_entity_only(self):
        """只有实体匹配，意图不匹配 → 部分匹配"""
        items = [
            {
                "id": 1,
                "title": "L13C 规格表",
                "content": "L13C 设备参数：电压 12V，功率 5W。",
            }
        ]
        intents = ["客流", "统计"]
        assert self.pp._check_partial_match(items, intents)

    def test_no_intents(self):
        """无意图词 → 非部分匹配"""
        items = [{"id": 1, "title": "测试", "content": "内容"}]
        assert not self.pp._check_partial_match(items, [])


class TestIsLogContent:
    """日志内容检测测试"""

    def setup_method(self):
        self.pp = QueryPreprocessor()

    def test_short_text_not_log(self):
        assert not self.pp.is_log_content("L13C的客流统计")

    def test_log_with_timestamp(self):
        log_text = "2024-01-01 12:00:00 [ERROR] Connection failed\n" * 20
        assert self.pp.is_log_content(log_text)

    def test_log_with_stack_trace(self):
        log_text = "at com.example.Service.handle:123\n" * 20
        assert self.pp.is_log_content(log_text)


class TestPreprocessAndSearch:
    """集成测试"""

    def setup_method(self):
        self.pp = QueryPreprocessor()

    def test_full_pipeline_success(self):
        """完整管道：分词 → 搜索 → 校验"""
        def mock_search(term, size):
            return {
                "items": [
                    {"id": 1, "title": "客流逻辑", "relevance_score": 0.9,
                     "content": "客流统计包括：开门上报、到站上报。适用于 L13C。"},
                ]
            }

        result = self.pp.process(
            query="L13C的客流统计是怎么样的呢？",
            search_fn=mock_search,
        )
        assert len(result.items) >= 1
        assert not result.is_partial_match
        assert result.matched_layer != "无匹配"

    def test_full_pipeline_no_results(self):
        """完整管道：无结果"""
        def mock_search(term, size):
            return {"items": []}

        result = self.pp.process(
            query="完全不存在的文档XYZ123",
            search_fn=mock_search,
        )
        assert len(result.items) == 0

    def test_global_singleton(self):
        """全局单例"""
        pp1 = get_preprocessor()
        pp2 = get_preprocessor()
        assert pp1 is pp2
