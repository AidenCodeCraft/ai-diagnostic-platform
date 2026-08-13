"""核心验证 — 只测纯逻辑，不加载重型模型"""
import sys
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')

p = 0; f = 0
def ck(name, cond):
    global p, f
    if cond: print(f"  [OK] {name}"); p += 1
    else: print(f"  [FAIL] {name}"); f += 1

print("=" * 50)
print("1. Provider Health")
from app.services.knowledge.provider_health import ProviderStats, ProviderHealthTracker, get_provider_health_tracker
s = ProviderStats(name="test")
s.record_success(100); s.record_success(200); s.record_failure("err")
ck("success_rate", abs(s.success_rate - 0.667) < 0.01)
ck("health_score > 0.5", s.health_score > 0.5)
t = ProviderHealthTracker()
t.record_success("a", 100); t.record_failure("b", "err")
ck("best_provider", t.get_best_provider(["a","b"]) == "a")
ck("empty_candidates", t.get_best_provider([]) is None)
ck("all_stats", t.get_all_stats()["a"]["success_rate"] == 1.0)
ck("singleton", get_provider_health_tracker() is get_provider_health_tracker())
t.reset()
ck("reset", len(t.get_all_stats()) == 0)

print("\n2. ProviderRegistry")
from app.services.knowledge.provider_registry import ProviderRegistry
reg = ProviderRegistry()
ck("health_tracker", reg.health_tracker is not None)
ck("enable_health", reg._enable_health is True)

print("\n3. DeepSeek Analysis")
from app.services.chat.deepseek_analysis import DeepSeekQuestionAnalyzer
a = DeepSeekQuestionAnalyzer()
ck("enhance_low", a.should_enhance({"is_diagnostic":True,"confidence":0.4}))
ck("no_enhance_nondiag", not a.should_enhance({"is_diagnostic":False,"confidence":0.4}))
ck("no_enhance_high", not a.should_enhance({"is_diagnostic":True,"confidence":0.8}))
parsed = a._parse_response('{"is_diagnostic":true,"confidence":0.9}')
ck("parse_valid", parsed["confidence"] == 0.9)
merged = a._merge_results(
    {"is_diagnostic":True,"score":3,"confidence":0.4,"topics":["a"],"sub_questions":["q1"]},
    {"is_diagnostic":True,"domains":["b"],"sub_questions":["q2"],"urgency":"high","confidence":0.85,"reasoning":"t"}
)
ck("merge_enhanced", merged["llm_enhanced"] is True)
ck("merge_conf", merged["confidence"] == 0.85)

print("\n4. TokenCounter")
from app.services.core.token_counter import TokenCounter, get_token_counter
c = TokenCounter()
ck("limit_v4", c.get_context_limit("deepseek-v4") == 1_000_000)
ck("limit_gpt4o", c.get_context_limit("gpt-4o") == 128_000)
ck("limit_unknown", c.get_context_limit("unknown") == 32_000)
ck("prefix_v4flash", c.get_context_limit("deepseek-v4-flash") == 1_000_000)
ck("chat_budget", c.get_chat_budget("deepseek-chat") == 38_400)
ck("rag_budget", c.get_rag_budget("deepseek-v4") == 696_000)
ck("min_budget", c.get_chat_budget("gpt-4", ratio=0.1) >= 4_000)
ck("count_hello", c.count("hello") == 1)
ck("singleton", get_token_counter() is get_token_counter())

print("\n5. Configs")
from app.services.core.config import DEFAULT_CONFIG, RerankerConfig
ck("chat_budget_v4", DEFAULT_CONFIG.context.get_chat_budget("deepseek-v4") == 600_000)
ck("rag_budget_v4", DEFAULT_CONFIG.context.get_rag_budget("deepseek-v4") == 696_000)
cfg = RerankerConfig()
ck("fallback_enabled", cfg.llm_fallback_enabled is True)
ck("fallback_threshold", cfg.llm_fallback_threshold == 0.3)
ck("fallback_timeout", cfg.llm_fallback_timeout == 3.0)

print("\n6. LLM Reranker (no model load)")
from app.services.knowledge.llm_reranker import LLMReranker
r = LLMReranker(model="deepseek-chat")
ck("trigger_low", r.should_trigger([0.2]))
ck("no_trigger_high", not r.should_trigger([0.9]))
ck("no_trigger_empty", not r.should_trigger([]))
pr = r._parse_llm_response('{"ranked":[{"index":0,"score":0.95}]}', [(0,"text")], 3)
ck("parse_valid", len(pr)==1 and pr[0][1]==0.95)
pr2 = r._parse_llm_response("bad", [(0,"text")], 3)
ck("parse_invalid", pr2 == [])
pr3 = r._parse_llm_response('```json\n{"ranked":[{"index":0,"score":0.8}]}\n```', [(0,"text")], 3)
ck("parse_fence", len(pr3)==1 and pr3[0][1]==0.8)
pr4 = r._parse_llm_response('{"ranked":[{"index":99,"score":0.9}]}', [(0,"text")], 3)
ck("parse_oob", pr4 == [])

print()
print("=" * 50)
print(f"RESULTS: {p} passed, {f} failed")
print("ALL PASSED!" if f == 0 else "SOME FAILED!")
print("=" * 50)
