"""DeepSeek 视觉/OCR Provider（对话截图识别）。

两条能力：
  - ocr()      → POST /tools/ocr，返回原样文本（日志截图首选，保真）
  - describe() → chat/completions + image_url，返回模型描述（UI/图表兜底）

为什么放在 providers 层：AGENTS.md 要求 LLM 调用必须经 Provider 抽象，
不允许在业务代码里直连 SDK/HTTP。业务侧只依赖 VisionProviderError 与返回结构。
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.providers.deepseek_provider import _load_admin_llm_config

logger = get_logger(__name__)

DEFAULT_OCR_PATH = "/tools/ocr"
DEFAULT_CHAT_PATH = "/chat/completions"


class VisionProviderError(RuntimeError):
    """视觉/OCR 调用失败（网络、鉴权、格式、超时）。"""


class DeepSeekVisionProvider:
    """DeepSeek OCR + 图像理解。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 90.0,
    ) -> None:
        file_cfg = _load_admin_llm_config()
        self.api_key = (
            api_key
            or os.getenv("DEEPSEEK_API_KEY", "")
            or str(getattr(settings, "DEEPSEEK_API_KEY", "") or "")
            or file_cfg.get("api_key", "")
        )
        raw_base = (
            base_url
            or os.getenv("DEEPSEEK_BASE_URL", "")
            or file_cfg.get("base_url")
            or "https://api.deepseek.com/v1/chat/completions"
        )
        # 归一成 "…/v1" 根地址：/v1/chat/completions → /v1
        self.api_root = str(raw_base).split("/chat/completions")[0].rstrip("/")
        self.model = (
            model
            or os.getenv("DEEPSEEK_VISION_MODEL", "")
            or str(getattr(settings, "DEEPSEEK_VISION_MODEL", "") or "")
            or "deepseek-flash"
        )
        self.timeout = max(float(timeout), 30.0)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    def ocr(self, data: bytes, filename: str) -> Dict[str, Any]:
        """识别图片中的文字（原样返回，不做任何清理）。"""
        if not self.available:
            raise VisionProviderError("未配置 DEEPSEEK_API_KEY，无法调用 OCR")

        url = f"{self.api_root}{DEFAULT_OCR_PATH}"
        files = {"file": (filename or "image.png", data)}
        payload = {"purpose": "text_recognition"}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=payload,
                    files=files,
                )
        except httpx.HTTPError as exc:
            raise VisionProviderError(f"OCR 请求失败: {exc}") from exc

        if response.status_code != 200:
            raise VisionProviderError(
                f"OCR 返回 {response.status_code}: {response.text[:300]}"
            )

        body = response.json()
        pages = body.get("pages") or []
        text = "\n".join(str(page.get("text", "")) for page in pages).strip()
        return {
            "text": text,
            "pages": len(pages),
            "usage": body.get("usage") or {},
            "raw_id": body.get("id"),
        }

    # ------------------------------------------------------------------
    # 视觉理解
    # ------------------------------------------------------------------

    def describe(self, data: bytes, mime: str, prompt: str) -> Dict[str, Any]:
        """让模型描述图片（用于 OCR 信息不足的场景）。"""
        if not self.available:
            raise VisionProviderError("未配置 DEEPSEEK_API_KEY，无法调用视觉模型")

        encoded = base64.b64encode(data).decode("utf-8")
        data_url = f"data:{mime or 'image/png'};base64,{encoded}"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "stream": False,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.api_root}{DEFAULT_CHAT_PATH}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise VisionProviderError(f"视觉请求失败: {exc}") from exc

        if response.status_code != 200:
            raise VisionProviderError(
                f"视觉模型返回 {response.status_code}: {response.text[:300]}"
            )

        body = response.json()
        choices = body.get("choices") or []
        text = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
            text = content if isinstance(content, str) else str(content)
        return {"text": text.strip(), "usage": body.get("usage") or {}}


def prompt_path(name: str = "vision_image_understanding_v1.txt") -> Path:
    """视觉提示词文件路径（版本化，禁止硬编码在代码里）。"""
    return Path(__file__).resolve().parent.parent / "prompts" / name


def load_vision_prompt(name: str = "vision_image_understanding_v1.txt") -> str:
    path = prompt_path(name)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VisionProviderError(f"读取视觉提示词失败: {path} ({exc})") from exc


def get_vision_provider() -> DeepSeekVisionProvider:
    return DeepSeekVisionProvider()
