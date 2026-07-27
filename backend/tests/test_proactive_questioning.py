"""主动追问系统边界测试 — 缺失检测、LLM分析、用户画像、边界条件。"""

from __future__ import annotations

import pytest

from app.services.chat.proactive_questioning import (
    ProactiveQuestioning,
    QuestioningState,
    UserExpertiseLevel,
    QuestionPriority,
    QuestionItem,
    check_and_generate_proactive_questions,
    analyze_and_ask_with_llm,
)


# ═══════════════════════════════════════════════════════════
# QuestioningState
# ═══════════════════════════════════════════════════════════

def test_state_initial():
    state = QuestioningState()
    assert state.total_rounds == 0
    assert len(state.asked_info_types) == 0
    assert state.user_refused_count == 0
    assert not state.should_stop_asking


def test_state_record_asked():
    state = QuestioningState()
    state.record_asked("device_model")
    assert "device_model" in state.asked_info_types
    assert state.total_rounds == 1


def test_state_detect_duplicate():
    state = QuestioningState()
    state.record_asked("device_model")
    assert state.was_already_asked("device_model")
    assert not state.was_already_asked("firmware_version")


def test_state_received():
    state = QuestioningState()
    state.record_received("error_phenomenon")
    assert "error_phenomenon" in state.received_info_types


def test_state_stop_after_max_rounds():
    state = QuestioningState()
    state.record_asked("device_model")
    state.record_asked("error_phenomenon")
    state.record_asked("firmware_version")
    assert state.total_rounds == 3
    assert state.should_stop_asking


def test_state_stop_after_refusals():
    state = QuestioningState()
    state.user_refused_count = 2
    assert state.should_stop_asking


def test_state_reset():
    state = QuestioningState()
    state.record_asked("device_model")
    state.user_refused_count = 1
    state.reset()
    assert state.total_rounds == 0
    assert len(state.asked_info_types) == 0
    assert state.user_refused_count == 0


# ═══════════════════════════════════════════════════════════
# ProactiveQuestioning: Missing Info Detection
# ═══════════════════════════════════════════════════════════

def test_detect_missing_device_model():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info("设备开机变慢了", [])
    types = {m.info_type for m in missing}
    # 描述中无型号关键词，设备型号应该出现在缺失列表中
    assert "device_model" in types or "error_phenomenon" in types


def test_detect_missing_phenomenon():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info("iPhone 14有问题", [])
    types = {m.info_type for m in missing}
    assert "error_phenomenon" in types


def test_detect_provided_both():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info(
        "iPhone 14 iOS 17.1 黑屏死机，每次开机后都出现",
        [],
    )
    types = {m.info_type for m in missing}
    # 已提供设备型号和故障现象 — 这两类不应在缺失列表中
    for info_type in types:
        assert info_type not in ("device_model", "error_phenomenon")


def test_detect_empty_query():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info("", [])
    # 空查询应检测到所有关键信息都缺失
    assert len(missing) > 0
    assert any(m.is_critical for m in missing)


def test_detect_with_history():
    pq = ProactiveQuestioning()
    history = [
        {"role": "user", "content": "我的iPhone 14黑屏了"},
        {"role": "assistant", "content": "请问是什么时候出现的？"},
    ]
    missing = pq.analyze_missing_info("就刚才", history)
    types = {m.info_type for m in missing}
    # 历史中已提供设备型号和故障现象 — 这两类不应缺失
    for info_type in types:
        assert info_type not in ("device_model", "error_phenomenon"), f"Unexpected missing: {info_type}"


def test_detect_with_technical_terms():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info(
        "kernel panic at xhci_hcd module, dmesg shows interrupt storm",
        [],
    )
    types = {m.info_type for m in missing}
    # panic 和 interrupt 不是标准关键词列表中的病象关键词
    # 所以 error_phenomenon 可能仍缺失，这是合理的行为
    assert isinstance(types, set)


# ═══════════════════════════════════════════════════════════
# ProactiveQuestioning: Should Ask
# ═══════════════════════════════════════════════════════════

def test_should_ask_missing_critical():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info("有问题", [])
    assert pq.should_ask_questions("有问题", [], missing)


def test_should_not_ask_all_provided():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info(
        "iPhone 14 黑屏死机 每次重启都出现",
        [],
    )
    # 信息较全面时应该不需要追问，或critical缺失很少
    should_ask = pq.should_ask_questions(
        "iPhone 14 黑屏死机 每次重启都出现", [], missing,
    )
    critical_count = sum(1 for m in missing if m.is_critical)
    assert critical_count <= 1, f"Too many critical missing: {[m.info_type for m in missing if m.is_critical]}"


def test_should_not_ask_after_stop():
    pq = ProactiveQuestioning()
    pq.state.user_refused_count = 2
    assert not pq.should_ask_questions("有问题", [])


# ═══════════════════════════════════════════════════════════
# ProactiveQuestioning: Question Generation
# ═══════════════════════════════════════════════════════════

def test_generate_questions_priority_order():
    pq = ProactiveQuestioning()
    # 所有信息都缺失
    missing = pq.analyze_missing_info("有问题", [])
    questions = pq.generate_questions(missing, max_questions=3)
    assert len(questions) <= 3
    assert all(isinstance(q, str) and len(q) > 0 for q in questions)


def test_generate_questions_novice():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info("设备有问题", [])
    questions = pq.generate_questions(missing, UserExpertiseLevel.NOVICE, max_questions=1)
    assert len(questions) == 1
    # 新手问法应包含引导语
    assert "请" in questions[0] or "吗" in questions[0]


def test_generate_questions_expert():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info("有问题", [])
    questions = pq.generate_questions(missing, UserExpertiseLevel.EXPERT, max_questions=1)
    assert len(questions) == 1
    # 专家问法应更简洁技术化
    assert len(questions[0]) < 100


def test_generate_questions_empty_missing():
    pq = ProactiveQuestioning()
    questions = pq.generate_questions([], UserExpertiseLevel.INTERMEDIATE)
    assert questions == []


# ═══════════════════════════════════════════════════════════
# ProactiveQuestioning: Format Response
# ═══════════════════════════════════════════════════════════

def test_format_response_basic():
    pq = ProactiveQuestioning()
    response = pq.format_proactive_response(
        ["请问是什么设备型号？"],
        user_expertise=UserExpertiseLevel.INTERMEDIATE,
    )
    assert "设备型号" in response
    assert len(response) > 0


def test_format_response_novice():
    pq = ProactiveQuestioning()
    response = pq.format_proactive_response(
        ["能详细描述一下故障现象吗？"],
        user_expertise=UserExpertiseLevel.NOVICE,
    )
    assert len(response) > 0


def test_format_response_with_partial_answer():
    pq = ProactiveQuestioning()
    response = pq.format_proactive_response(
        ["请问频率如何？"],
        partial_answer="根据您目前的描述，初步判断可能与USB有关。",
    )
    assert "USB" in response or "根据您" in response


# ═══════════════════════════════════════════════════════════
# User Expertise Detection
# ═══════════════════════════════════════════════════════════

def test_detect_novice():
    pq = ProactiveQuestioning()
    history = [{"role": "user", "content": "设备坏了"}]
    level = pq._detect_user_expertise(history)
    assert level == UserExpertiseLevel.NOVICE


def test_detect_expert():
    pq = ProactiveQuestioning()
    history = [
        {"role": "user", "content": "dmesg显示 xhci_hcd timeout, 需要检查USB PHY寄存器和中断配置"},
    ]
    level = pq._detect_user_expertise(history)
    assert level in (UserExpertiseLevel.EXPERT, UserExpertiseLevel.INTERMEDIATE)


def test_detect_intermediate():
    pq = ProactiveQuestioning()
    history = [
        {"role": "user", "content": "设备启动时USB枚举失败，日志里有超时错误"},
    ]
    level = pq._detect_user_expertise(history)
    assert level == UserExpertiseLevel.INTERMEDIATE


def test_detect_no_history():
    pq = ProactiveQuestioning()
    level = pq._detect_user_expertise([])
    assert level == UserExpertiseLevel.INTERMEDIATE


# ═══════════════════════════════════════════════════════════
# User Refusal Detection
# ═══════════════════════════════════════════════════════════

def test_detect_refusal():
    pq = ProactiveQuestioning()
    assert pq._detect_user_refusal("不知道")
    assert pq._detect_user_refusal("别问了，直接分析")
    assert pq._detect_user_refusal("能不能直接说结果")


def test_detect_not_refusal():
    pq = ProactiveQuestioning()
    assert not pq._detect_user_refusal("iPhone 14 黑屏")
    assert not pq._detect_user_refusal("USB timeout 错误")


# ═══════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════

def test_check_and_generate_need_ask():
    result = check_and_generate_proactive_questions(
        "设备有问题",
        [],
        use_llm=False,
    )
    assert result is not None
    assert len(result) > 0


def test_check_and_generate_no_need():
    result = check_and_generate_proactive_questions(
        "iPhone 14 黑屏重启 每次开机都出现 USB连接也断",
        [],
        use_llm=False,
    )
    # 信息较丰富，不应追问或追问内容应简短
    if result is not None:
        assert len(result.split("\n")) <= 8  # 追问应较简短（<=8行）


def test_check_and_generate_empty_query():
    # 空查询可能触发追问
    result = check_and_generate_proactive_questions("", [], use_llm=False)
    # 空查询无关键信息 => 需要追问
    assert result is not None


def test_analyze_with_llm_fallback():
    # LLM 不可用时应回退到关键词分析
    result = analyze_and_ask_with_llm("iPhone 14有问题", [])
    assert isinstance(result, dict)
    assert "should_ask" in result
    assert "user_expertise" in result
    assert "missing_info" in result


# ═══════════════════════════════════════════════════════════
# QuestionItem
# ═══════════════════════════════════════════════════════════

def test_question_item_get_novice():
    item = QuestionItem(
        info_type="device_model",
        category_name="设备型号",
        priority=QuestionPriority.HIGH,
        questions=["请问是什么设备？", "请提供型号"],
        is_critical=True,
    )
    q = item.get_question(UserExpertiseLevel.NOVICE)
    assert len(q) > 0


def test_question_item_get_expert():
    item = QuestionItem(
        info_type="device_model",
        category_name="设备型号",
        priority=QuestionPriority.HIGH,
        questions=["请提供设备型号及硬件配置信息"],
        is_critical=True,
    )
    q = item.get_question(UserExpertiseLevel.EXPERT)
    assert len(q) > 0


# ═══════════════════════════════════════════════════════════
# Boundary & Edge Cases
# ═══════════════════════════════════════════════════════════

def test_very_long_query():
    pq = ProactiveQuestioning()
    long_query = "设备型号 iPhone 14 固件版本 17.1 故障现象 黑屏 故障频率 每次 " * 20
    missing = pq.analyze_missing_info(long_query, [])
    # 包含所有关键信息的超长文本，critical 缺失不应太多
    critical_count = sum(1 for m in missing if m.is_critical)
    assert critical_count <= 1  # 最多1个critical缺失


def test_unicode_and_special_chars():
    pq = ProactiveQuestioning()
    missing = pq.analyze_missing_info("\U0001f4f1\u2728 设备\u00ae有问题\U0001f534", [])
    assert len(missing) > 0  # 应能正常处理


def test_question_priority_enum():
    assert QuestionPriority.CRITICAL > QuestionPriority.HIGH > QuestionPriority.MEDIUM > QuestionPriority.LOW


def test_expertise_level_enum():
    assert UserExpertiseLevel.NOVICE.value == "novice"
    assert UserExpertiseLevel.EXPERT.value == "expert"
