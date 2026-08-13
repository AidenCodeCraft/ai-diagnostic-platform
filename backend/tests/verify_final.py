"""最终验证脚本 — 所有新模块功能验证"""
import sys
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} {detail}")
        failed += 1

print("=" * 50)
print("FULL VERIFICATION")
print("=" * 50)

# 1. Provider Health
print("\n1. Provider Health")
from app.services.knowledge.provider_health import ProviderStats, ProviderHealthTracker, get_provider_health_tracker
s = ProviderStats(name="test")
s.record_success(100); s.record_success(200); s.record_failure("err")
check("success_rate ~0.667", abs(s.success_rate - 0.667) < 0.01)
check("health_score > 0.5", s.health_score > 0.5)
t = ProviderHealthTracker()
t.record_success("a", 100); t.record_failure("b", "err")
check("get_best_provider selects healthy", t.get_best_provider(["a", "b"]) == "a")
check("get_best_provider empty", t.get_best_provider([]) is None)
check("get_all_stats has data", t.get_all_stats()["a"]["success_rate"] == 1.0)
check("singleton works", get_provider_health_tracker() is get_provider_health_tracker())
t.reset()
check("reset clears stats", len(t.get_all_stats()) == 0)

# 2. ProviderRegistry
print("\n2. ProviderRegistry")
from app.services.knowledge.provider_registry import ProviderRegistry
reg = ProviderRegistry()
check("health_tracker available", reg.health_tracker is not None)
check("enable_health flag", reg._enable_health is True)

# 3. DeepSeek Analysis
print("\n3. DeepSeek Analysis")
from app.services.chat.deepseek_analysis import DeepSeekQuestionAnalyzer
a = DeepSeekQuestionAnalyzer()
check("enhance low-conf diagnostic", a.should_enhance({"is_diagnostic": True, "confidence": 0.4}))
check("no enhance non-diagnostic", not a.should_enhance({"is_diagnostic": False, "confidence": 0.4}))
check("no enhance high-conf", not a.should_enhance({"is_diagnostic": True, "confidence": 0.8}))
parsed = a._parse_response('{"is_diagnostic":true,"confidence":0.9}')
check("parse valid JSON", parsed["confidence"] == 0.9)
merged = a._merge_results(
    {"is_diagnostic": True, "score": 3, "confidence": 0.4, "topics": ["a"], "sub_questions": ["q1"]},
    {"is_diagnostic": True, "domains": ["b"], "sub_questions": ["q2"], "urgency": "high", "confidence": 0.85, "reasoning": "t"}
)
check("merge llm_enhanced flag", merged["llm_enhanced"] is True)
check("merge confidence", merged["confidence"] == 0.85)

# 4. TokenCounter
print("\n4. TokenCounter")
from app.services.core.token_counter import TokenCounter, get_token_counter
c = TokenCounter()
check("context_limit deepseek-v4", c.get_context_limit("deepseek-v4") == 1_000_000)
check("context_limit gpt-4o", c.get_context_limit("gpt-4o") == 128_000)
check("context_limit unknown", c.get_context_limit("unknown") == 32_000)
check("prefix match v4-flash", c.get_context_limit("deepseek-v4-flash") == 1_000_000)
check("chat_budget deepseek-chat", c.get_chat_budget("deepseek-chat") == 38_400)
check("rag_budget deepseek-v4", c.get_rag_budget("deepseek-v4") == 696_000)
check("min_budget enforced", c.get_chat_budget("gpt-4", ratio=0.1) >= 4_000)
check("tiktoken count hello", c.count("hello") == 1)
check("singleton", get_token_counter() is get_token_counter())

# 5. ContextConfig
print("\n5. ContextConfig")
from app.services.core.config import DEFAULT_CONFIG, RerankerConfig
check("get_chat_budget v4", DEFAULT_CONFIG.context.get_chat_budget("deepseek-v4") == 600_000)
check("get_rag_budget v4", DEFAULT_CONFIG.context.get_rag_budget("deepseek-v4") == 696_000)
cfg = RerankerConfig()
check("llm_fallback_enabled", cfg.llm_fallback_enabled is True)
check("llm_fallback_threshold", cfg.llm_fallback_threshold == 0.3)
check("llm_fallback_timeout", cfg.llm_fallback_timeout == 3.0)

# 6. ContextManager
print("\n6. ContextManager")
from app.services.chat.context_manager import ContextManager
mgr = ContextManager(model="deepseek-v4")
check("max_tokens v4", mgr.max_tokens == 600_000)
check("should_compress 25 msgs", ContextManager.should_compress([{"role": "user", "content": "x"}] * 25))
check("no compress 5 msgs", not ContextManager.should_compress([{"role": "user", "content": "x"}] * 5))
default_mgr = ContextManager()
check("default max_tokens", default_mgr.max_tokens == 8000)

# 7. RAGService
print("\n7. RAGService")
from app.services.rag.rag_service import RAGService
rag = RAGService.__new__(RAGService)
rag.model = "deepseek-chat"
rag.config = DEFAULT_CONFIG
check("llm_fallback config", rag.config.reranker.llm_fallback_enabled is True)
est = rag._estimate_single_text_tokens("hello")
check("estimate tokens > 0", est > 0)
trunc = rag._truncate_text_to_tokens("A" * 1000, 5)
check("truncate works", len(trunc) < 50)

# 8. LLM Reranker
print("\n8. LLM Reranker")
from app.services.knowledge.llm_reranker import LLMReranker
r = LLMReranker(model="deepseek-chat")
check("trigger low CE", r.should_trigger([0.2]))
check("no trigger high CE", not r.should_trigger([0.9]))
check("no trigger empty", not r.should_trigger([]))
parsed_r = r._parse_llm_response('{"ranked":[{"index":0,"score":0.95}]}', [(0, "text")], 3)
check("parse valid rerank", len(parsed_r) == 1 and parsed_r[0][1] == 0.95)
parsed_r2 = r._parse_llm_response("bad json", [(0, "text")], 3)
check("parse invalid returns []", parsed_r2 == [])
parsed_r3 = r._parse_llm_response('```json\n{"ranked":[{"index":0,"score":0.8}]}\n```', [(0, "text")], 3)
check("parse markdown fence", len(parsed_r3) == 1 and parsed_r3[0][1] == 0.8)
parsed_r4 = r._parse_llm_response('{"ranked":[{"index":99,"score":0.9}]}', [(0, "text")], 3)
check("parse out-of-bounds filtered", parsed_r4 == [])

# Summary
print()
print("=" * 50)
print(f"RESULTS: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL VERIFICATIONS PASSED!")
else:
    print("SOME VERIFICATIONS FAILED!")
print("=" * 50)
