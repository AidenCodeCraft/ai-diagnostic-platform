"""
Python SDK - DiagnosticClient

Usage:
    from ai_diagnostic import DiagnosticClient

    client = DiagnosticClient("http://localhost:8000/api/v1")
    client.login("admin", "password123")

    # 上传并分析日志
    result = client.analyze_log("test.log")
    print(result.summary)

    # 对话
    session = client.create_session("诊断会话")
    reply = client.chat(session.id, "这个错误是什么原因？")
    print(reply)

    # 搜索
    results = client.search("kernel panic", "logs")
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import httpx


class AnalysisResult:
    """分析结果"""
    def __init__(self, data: dict):
        self.id: int = data.get("id", 0)
        self.log_id: int = data.get("log_id", 0)
        self.status: str = data.get("status", "")
        self.summary: str = data.get("summary", "")
        self.root_cause: str = data.get("root_cause", "")
        self.confidence: float = data.get("confidence", 0.0)
        self.next_steps: list[str] = data.get("next_steps", [])
        self.diagnosis_markdown: str = data.get("diagnosis_markdown", "")
        self._raw: dict = data

    def __repr__(self):
        return f"<AnalysisResult id={self.id} status={self.status}>"


class ChatReply:
    """对话回复"""
    def __init__(self, data: dict):
        self.role: str = data.get("role", "assistant")
        self.content: str = data.get("content", "")
        self._raw: dict = data

    def __repr__(self):
        preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        return f"<ChatReply {preview}>"


class Session:
    """会话"""
    def __init__(self, data: dict):
        self.id: int = data.get("id", 0)
        self.title: str = data.get("title", "")
        self.model: str = data.get("model", "")
        self._raw: dict = data

    def __repr__(self):
        return f"<Session id={self.id} title={self.title!r}>"


class DiagnosticClient:
    """AI Diagnostic Platform Python SDK"""

    def __init__(self, base_url: str = "http://localhost:8000/api/v1", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._token: Optional[str] = None

    # ── Auth ────────────────────────────────────────────────

    def login(self, username: str, password: str) -> str:
        """登录并获取 JWT token"""
        resp = self._client.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("access_token", "")
        self._client.headers["Authorization"] = f"Bearer {self._token}"
        return self._token  # type: ignore[return-type]

    def set_token(self, token: str):
        """手动设置 token"""
        self._token = token
        self._client.headers["Authorization"] = f"Bearer {token}"

    # ── Logs ────────────────────────────────────────────────

    def upload_log(self, file_path: str | Path, description: str = "") -> dict:
        """上传日志文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"日志文件不存在: {file_path}")

        with open(path, "rb") as f:
            resp = self._client.post(
                f"{self.base_url}/logs/upload",
                files={"file": (path.name, f)},
                data={"description": description},
            )
        resp.raise_for_status()
        return resp.json()

    def get_log(self, log_id: int) -> dict:
        """获取日志详情"""
        resp = self._client.get(f"{self.base_url}/logs/{log_id}")
        resp.raise_for_status()
        return resp.json()

    # ── Analysis ────────────────────────────────────────────

    def run_analysis(self, log_id: int, model: str = "deepseek-v4-flash", query: str = "") -> dict:
        """触发分析任务"""
        resp = self._client.post(
            f"{self.base_url}/analyses/run",
            json={"log_id": log_id, "model": model, "query": query},
        )
        resp.raise_for_status()
        return resp.json()

    def get_analysis(self, analysis_id: int) -> AnalysisResult:
        """获取分析结果"""
        resp = self._client.get(f"{self.base_url}/analyses/{analysis_id}")
        resp.raise_for_status()
        return AnalysisResult(resp.json())

    def analyze_log(
        self,
        file_path: str | Path,
        model: str = "deepseek-v4-flash",
        query: str = "请分析此日志中的错误",
        poll_interval: float = 2.0,
        max_wait: float = 120.0,
    ) -> AnalysisResult:
        """
        上传日志文件并等待分析完成（一站式 API）

        Args:
            file_path: 日志文件路径
            model: 模型名称
            query: 分析查询
            poll_interval: 轮询间隔（秒）
            max_wait: 最大等待时间（秒）

        Returns:
            AnalysisResult: 分析结果
        """
        # 上传
        upload_result = self.upload_log(file_path, query)
        log_id = upload_result.get("id")
        if not log_id:
            raise RuntimeError("上传失败：未返回日志 ID")

        # 触发分析
        analysis_result = self.run_analysis(log_id, model, query)
        analysis_id = analysis_result.get("id")
        if not analysis_id:
            raise RuntimeError("分析任务创建失败")

        # 轮询等待完成
        elapsed = 0.0
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval
            result = self.get_analysis(analysis_id)
            if result.status in ("completed", "failed"):
                return result

        raise TimeoutError(f"分析超时（已等待 {max_wait} 秒）")

    # ── Chat ────────────────────────────────────────────────

    def create_session(self, title: str = "新对话", model: str = "deepseek-v4-flash") -> Session:
        """创建对话会话"""
        resp = self._client.post(
            f"{self.base_url}/chat-sessions",
            json={"title": title, "model": model},
        )
        resp.raise_for_status()
        return Session(resp.json())

    def list_sessions(self) -> list[Session]:
        """列出所有会话"""
        resp = self._client.get(f"{self.base_url}/chat-sessions")
        resp.raise_for_status()
        data = resp.json()
        return [Session(s) for s in data.get("items", [])]

    def chat(self, session_id: int, message: str, model: str = "deepseek-v4-flash") -> ChatReply:
        """发送对话消息（非流式）"""
        resp = self._client.post(
            f"{self.base_url}/chat-sessions/{session_id}/chat",
            json={"message": message, "model": model},
        )
        resp.raise_for_status()
        return ChatReply(resp.json())

    def get_messages(self, session_id: int) -> list[dict]:
        """获取会话消息"""
        resp = self._client.get(f"{self.base_url}/chat-sessions/{session_id}/messages")
        resp.raise_for_status()
        return resp.json()

    # ── Knowledge ───────────────────────────────────────────

    def search_knowledge(self, query: str, limit: int = 10) -> list[dict]:
        """搜索知识库"""
        resp = self._client.get(
            f"{self.base_url}/knowledge/search",
            params={"q": query, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    def create_knowledge(self, title: str, content: str, category: str = "note") -> dict:
        """创建知识文档"""
        resp = self._client.post(
            f"{self.base_url}/knowledge",
            json={"title": title, "content": content, "category": category},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Reports ─────────────────────────────────────────────

    def get_reports(self, page: int = 1, page_size: int = 20) -> dict:
        """获取报告列表"""
        resp = self._client.get(
            f"{self.base_url}/reports",
            params={"page": page, "page_size": page_size},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Search ──────────────────────────────────────────────

    def search(self, query: str, type: str = "all", limit: int = 20) -> dict:
        """统一搜索"""
        resp = self._client.get(
            f"{self.base_url}/search",
            params={"q": query, "type": type, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Admin ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """获取系统统计"""
        resp = self._client.get(f"{self.base_url}/admin/stats")
        resp.raise_for_status()
        return resp.json()

    # ── Cleanup ─────────────────────────────────────────────

    def close(self):
        """关闭 HTTP 客户端"""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
