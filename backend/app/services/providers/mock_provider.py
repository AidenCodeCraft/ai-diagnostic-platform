from __future__ import annotations

import time
from typing import Any, Dict, Generator, List

from app.services.providers.base import BaseProvider


class MockProvider(BaseProvider):
    name = "mock"

    def __init__(self, **kwargs):
        super().__init__()
        # Accept but ignore config kwargs (api_key, base_url, model) from provider registry

    def generate_summary(self, log_content: str, events: list[Dict[str, Any]]) -> Dict[str, Any]:
        error_events = [event for event in events if event.get("is_error")]
        module_names = [str(event.get("module", "system")).lower() for event in error_events if event.get("module")]
        module_hint = module_names[0] if module_names else "设备"
        log_content_lower = (log_content or "").lower()
        log_hint = "USB" if "usb" in log_content_lower else module_hint.capitalize()
        if error_events:
            summary = f"在 {log_hint} 模块中检测到 {len(error_events)} 个错误事件，很可能是设备端通信超时或故障导致。"
        else:
            summary = "日志中未检测到明显的错误模式，设备运行状态正常。"

        return {
            "model": self.name,
            "summary": summary,
            "confidence": 0.7,
            "root_cause": "设备端通信故障或超时。" if error_events else "当前日志数据中未发现明确的根因。",
            "next_steps": [
                "检查受影响的设备接口及时序行为",
                "确认线缆、驱动及外设状态",
                "如有条件，请上传更详细的日志进行深度分析"
            ],
            "event_count": len(events),
            "error_count": len(error_events),
        }

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Return a mock conversational reply with thinking chain."""
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        if not last_user.strip():
            return self._greeting()

        if "日志" in last_user or "log" in last_user.lower():
            return (
                "我注意到你提到了日志。\n\n"
                "你可以通过输入框左侧的 📎 按钮上传日志文件（支持 .txt / .log / .zip 格式），"
                "我会自动完成以下分析流程：\n\n"
                "1. **日志解析** → 提取结构化事件和时间线\n"
                "2. **规则匹配** → 检测已知错误模式\n"
                "3. **知识检索** → 搜索历史相似案例\n"
                "4. **AI 综合分析** → 生成诊断报告\n\n"
                "请上传你的日志文件一起分析。"
            )
        if "错误" in last_user or "error" in last_user.lower() or "故障" in last_user:
            return (
                "根据你的描述，可能的故障原因如下：\n\n"
                "**初步分析：**\n"
                "- 🔍 设备通信故障或超时\n"
                "- 🔍 驱动模块加载异常\n\n"
                "**建议：**\n"
                "1. 检查设备接口连接是否稳定\n"
                "2. 上传相关日志文件进行详细分析\n"
                "3. 确认驱动版本与固件是否匹配\n\n"
                "如需更精确的诊断，请上传日志文件。"
            )
        return (
            "收到你的消息。作为 AI 设备日志诊断助手，我可以帮你：\n\n"
            "- 📋 解析设备日志中的错误事件\n"
            "- 🎯 定位故障根因并给出置信度\n"
            "- 📝 提供修复建议和操作步骤\n"
            "- 📚 检索历史案例和知识库\n\n"
            "请上传日志文件或详细描述遇到的问题。"
        )

    @staticmethod
    def _greeting() -> str:
        return (
            "你好！我是 AI 设备日志诊断助手。\n\n"
            "我可以帮你分析和诊断设备故障，具体流程包括：\n\n"
            "1. **日志解析** → 提取错误事件和时间线\n"
            "2. **规则匹配** → 检测已知故障模式\n"
            "3. **知识检索** → 搜索历史案例\n"
            "4. **AI 综合分析** → 生成诊断报告\n\n"
            "请上传日志文件或描述你遇到的问题，我会立即开始分析。"
        )

    def chat_stream(self, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        """Simulate streaming with thinking chain — word-by-word with delays."""
        full = self.chat(messages)
        words = full.split(" ")
        for i, word in enumerate(words):
            suffix = " " if i < len(words) - 1 else ""
            yield word + suffix
            time.sleep(0.03)  # simulate token latency

