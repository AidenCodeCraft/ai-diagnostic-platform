"""Function Calling Agent — LLM 主动调用工具进行对话增强。

核心能力：
- LLM 可在对话中主动决定调用工具（知识搜索、日志解析等）
- 支持 OpenAI Function Calling 格式
- 支持工具调用循环（LLM → Tool → LLM → ...）
- 自动解析 tool_calls 并执行
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents.core.tool import Tool, ToolRegistry, ToolResult
from app.core.logging_config import get_logger
from app.services.knowledge.knowledge_service import KnowledgeService
from app.services.diagnostics.parser_service import LogParserService

logger = get_logger(__name__)

# 最大工具调用循环次数（防止无限循环）
MAX_TOOL_CALLS = 5


class KnowledgeSearchTool(Tool):
    """知识库搜索工具 — 可被 LLM 主动调用。"""

    name = "search_knowledge"
    description = (
        "Search the knowledge base for relevant information. "
        "Use this when the user asks about technical details, bug solutions, or device troubleshooting. "
        "Input: a search query string."
    )

    def __init__(self, db: Session):
        self.knowledge = KnowledgeService(db)

    def to_spec(self) -> Dict[str, Any]:
        """OpenAI Function Calling 格式规范。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find relevant information in the knowledge base.",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "").strip()
        if not query:
            return ToolResult(success=False, error="query is required")

        try:
            result = self.knowledge.search(query, page_size=3)
            items = result.get("items", [])

            if not items:
                return ToolResult(
                    success=True,
                    data={"message": "No relevant information found in knowledge base."},
                )

            # 格式化搜索结果
            formatted = []
            for item in items:
                formatted.append({
                    "title": item.get("title", "Untitled"),
                    "excerpt": item.get("snippet", "")[:300],
                    "relevance": item.get("relevance_score", 0),
                })

            return ToolResult(
                success=True,
                data={
                    "results": formatted,
                    "count": len(formatted),
                    "message": f"Found {len(formatted)} relevant document(s).",
                },
            )

        except Exception as e:
            logger.error(f"[KnowledgeSearchTool] Error: {e}")
            return ToolResult(success=False, error=str(e))


class QuickAnalysisTool(Tool):
    """快速日志分析工具 — 可被 LLM 主动调用。"""

    name = "analyze_log_snippet"
    description = (
        "Analyze a short log snippet (max 500 lines) for errors and patterns. "
        "Use this when the user provides a log excerpt in their message. "
        "Input: log text content."
    )

    def __init__(self, db: Session):
        self.parser = LogParserService()
        self.db = db

    def to_spec(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "log_content": {
                            "type": "string",
                            "description": "The log text content to analyze (max 500 lines).",
                        },
                    },
                    "required": ["log_content"],
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        log_content = kwargs.get("log_content", "").strip()
        if not log_content:
            return ToolResult(success=False, error="log_content is required")

        # 限制长度
        lines = log_content.split("\n")[:500]
        content = "\n".join(lines)

        try:
            # 使用通用解析器分析
            events = self.parser.parse_text(content)

            errors = [e for e in events if e.get("is_error")]
            warnings = [e for e in events if e.get("level") == "WARNING"]

            return ToolResult(
                success=True,
                data={
                    "total_events": len(events),
                    "errors": len(errors),
                    "warnings": len(warnings),
                    "error_classifications": list(set(
                        e.get("classification", "unknown") for e in errors
                    )),
                    "message": f"Parsed {len(events)} events, found {len(errors)} errors and {len(warnings)} warnings.",
                },
            )

        except Exception as e:
            logger.error(f"[QuickAnalysisTool] Error: {e}")
            return ToolResult(success=False, error=str(e))


class FunctionCallingAgent:
    """支持 Function Calling 的对话 Agent。

    工作流程：
    1. 用户消息 + 工具规范 → LLM
    2. LLM 返回：普通回复 或 tool_calls
    3. 如果有 tool_calls：执行工具 → 工具结果注入消息历史
    4. 重复步骤 1-3，直到 LLM 不再调用工具
    """

    def __init__(self, db: Session, provider_name: str = "deepseek"):
        self.db = db
        self.provider_name = provider_name
        self.tools = self._init_tools()

    def _init_tools(self) -> ToolRegistry:
        """初始化工具注册表。"""
        registry = ToolRegistry()
        registry.register(KnowledgeSearchTool(self.db))
        registry.register(QuickAnalysisTool(self.db))
        return registry

    def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        max_iterations: int = MAX_TOOL_CALLS,
    ) -> Dict[str, Any]:
        """执行支持工具调用的对话。

        Returns:
            {
                "content": str,  # 最终回复
                "tool_calls": List[Dict],  # 工具调用历史
                "iterations": int,  # 循环次数
            }
        """
        from app.services.knowledge.provider_registry import ProviderRegistry

        provider = ProviderRegistry().get_provider(self.provider_name)
        tool_specs = self.tools.list_specs()
        tool_call_history = []

        # 对话循环
        conversation = list(messages)
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            # 调用 LLM（暂时不使用 tools 参数，改为在 system prompt 中描述）
            # TODO: 当 Provider 支持原生 Function Calling 时，传入 tools 参数
            try:
                response = provider.chat(conversation)
            except Exception as e:
                logger.error(f"[FunctionCallingAgent] LLM error: {e}")
                return {
                    "content": f"Error: {e}",
                    "tool_calls": tool_call_history,
                    "iterations": iterations,
                }

            # 检测工具调用（简单实现：检测 JSON 格式的 tool_call）
            tool_calls = self._extract_tool_calls(response)

            if not tool_calls:
                # 没有工具调用，直接返回
                return {
                    "content": response,
                    "tool_calls": tool_call_history,
                    "iterations": iterations,
                }

            # 执行工具调用
            tool_results = []
            for call in tool_calls:
                tool_name = call.get("name", "")
                tool_args = call.get("arguments", {})

                logger.info(f"[FunctionCallingAgent] Calling tool: {tool_name} with args: {tool_args}")

                result = self.tools.execute(tool_name, **tool_args)
                tool_call_history.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                })
                tool_results.append({
                    "tool": tool_name,
                    "result": result.data if result.success else {"error": result.error},
                })

            # 将工具结果注入对话历史
            conversation.append({
                "role": "assistant",
                "content": f"[Called tools: {', '.join(c['name'] for c in tool_calls)}]",
            })
            conversation.append({
                "role": "user",
                "content": f"Tool results:\n{json.dumps(tool_results, ensure_ascii=False, indent=2)}",
            })

        # 达到最大迭代次数
        logger.warning(f"[FunctionCallingAgent] Reached max iterations: {max_iterations}")
        return {
            "content": "Maximum tool call iterations reached.",
            "tool_calls": tool_call_history,
            "iterations": iterations,
        }

    def _extract_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """从 LLM 响应中提取工具调用（简化实现）。

        检测格式：
        ```json
        {
          "tool_calls": [
            {"name": "search_knowledge", "arguments": {"query": "USB timeout"}}
          ]
        }
        ```
        """
        # 尝试提取 JSON 代码块
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "tool_calls" in data:
                    return data["tool_calls"]
            except json.JSONDecodeError:
                pass

        # 尝试直接解析整个响应为 JSON
        try:
            data = json.loads(response)
            if "tool_calls" in data:
                return data["tool_calls"]
        except json.JSONDecodeError:
            pass

        return []

    def get_system_prompt_with_tools(self) -> str:
        """生成包含工具规范的系统提示词。"""
        tool_specs = self.tools.list_specs()
        tool_descriptions = []

        for spec in tool_specs:
            if spec.get("type") == "function":
                func = spec["function"]
                tool_descriptions.append(
                    f"- **{func['name']}**: {func['description']}\n"
                    f"  Parameters: {json.dumps(func['parameters'], ensure_ascii=False)}"
                )

        tools_text = "\n".join(tool_descriptions)

        return f"""You are a professional diagnostic assistant with access to the following tools:

{tools_text}

When you need to use a tool, respond with a JSON block in this format:
```json
{{
  "tool_calls": [
    {{"name": "tool_name", "arguments": {{"param": "value"}}}}
  ]
}}
```

After receiving tool results, use them to provide a helpful answer to the user.
"""
