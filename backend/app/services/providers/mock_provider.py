from __future__ import annotations

import time
from typing import Any, Dict, Generator, List

from app.services.providers.base import BaseProvider


class MockProvider(BaseProvider):
    name = "mock"

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
        """Return a mock conversational reply."""
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        if not last_user.strip():
            return "你好！我是 AI 诊断助手。请上传日志文件或描述你遇到的问题，我会帮你分析。"

        if "日志" in last_user or "log" in last_user.lower():
            return "我注意到你提到了日志。你可以通过对话输入框上方的附件按钮上传日志文件（支持 .txt/.log/.tar.gz 格式），我会自动解析并分析其中的错误信息。"
        if "错误" in last_user or "error" in last_user.lower() or "故障" in last_user:
            return "根据你的描述，可能是设备通信故障或超时导致的。建议：\n1. 检查设备接口连接是否稳定\n2. 上传相关日志文件进行详细分析\n3. 确认驱动版本是否匹配"
        return f"收到你的消息。作为 AI 诊断助手，我可以帮你：\n- 分析设备日志中的错误\n- 定位故障根因\n- 提供修复建议\n\n请上传日志文件或详细描述遇到的问题。"

    def chat_stream(self, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        """Simulate streaming by yielding the reply word-by-word with small delays."""
        full = self.chat(messages)
        words = full.split(" ")
        for i, word in enumerate(words):
            suffix = " " if i < len(words) - 1 else ""
            yield word + suffix
            time.sleep(0.04)  # simulate token latency

