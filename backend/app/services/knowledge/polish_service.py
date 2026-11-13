"""知识库 AI 润色服务 — 用户草稿 → 模板化内容。

策略：
  1. LLM 可用且配置了真实 Provider（非 mock）→ 调用 LLM 润色；
  2. 对 LLM 输出做一致性校验（关键型号/数字保留、长度合理、模板校验通过）；
  3. 校验失败 / LLM 不可用 → 自动回退为规则规范化（保证按钮始终可用）；
  4. 返回格式与 `/knowledge/format/preview` 对齐，前端可直接用于预览与回填。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.knowledge.format_service import KnowledgeFormatService
from app.services.knowledge.normalizer import Normalizer
from app.services.knowledge.templates import get_template
from app.services.prompts.knowledge_polish import KnowledgePolishPrompt

logger = logging.getLogger(__name__)

# 关键 token：型号（FC09/L13C）、数字（9206/-5007）等，润色后必须保留
_KEY_TOKEN_RE = re.compile(r"[A-Za-z]{1,10}\d+[A-Za-z0-9._/-]*|\b\d{2,}\b")


class KnowledgePolishService:
    def __init__(self, db=None, provider=None) -> None:
        self.db = db
        self._explicit_provider = provider

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def polish(
        self,
        content: str,
        doc_type: Optional[str] = None,
        title: str = "",
        provider=None,
    ) -> Dict[str, Any]:
        if not (content or "").strip():
            raise ValueError("内容为空，无法润色")

        template = get_template(doc_type)
        template_name = template.name if template else (doc_type or "自由文档")
        guide = (
            template.guide if template
            else "自由格式：建议使用小标题分节、条目化表达，便于阅读与检索。"
        )
        skeleton = template.skeleton if template else ""

        source = "rule"
        notes: List[str] = []
        polished = ""

        llm = provider or self._explicit_provider or self._default_provider()
        if llm is not None:
            try:
                raw = llm.chat(
                    KnowledgePolishPrompt.build_messages(
                        content, template_name, guide, skeleton,
                    )
                )
                cleaned = self._clean_llm_output(raw)
                if self._acceptable(content, cleaned):
                    polished = cleaned
                    source = "llm"
                    notes.append(f"已由 AI 润色并规范为「{template_name}」格式")
                else:
                    notes.append("AI 润色结果未通过一致性校验，已回退为规则规范化")
            except Exception as exc:  # noqa: BLE001 - 润色失败自动回退
                logger.warning("[Polish] LLM polish failed: %s", exc)
                notes.append("AI 润色失败，已回退为规则规范化")

        if not polished:
            normalized = Normalizer().normalize(content, doc_type)
            polished = normalized.normalized_content
            notes.append("已按模板规则完成结构化整理")
            notes.extend(normalized.notes)

        preview = KnowledgeFormatService().preview(polished, doc_type, title)
        result = dict(preview)
        result["polished_content"] = preview.get("normalized_content", polished)
        result["source"] = source
        result["notes"] = self._dedupe(notes + list(preview.get("notes") or []))
        return result

    # ------------------------------------------------------------------
    # Provider
    # ------------------------------------------------------------------

    def _default_provider(self):
        """解析后台配置的默认模型并返回可用 Provider；全部不可用时返回 None。

        注意：settings.LLM_PROVIDER 默认是 mock（聊天通过 session.model 显式指定
        模型），因此润色不能直接 get_provider(None)，必须先读取后台「LLM 配置」的
        models 列表，按 isDefault → 有 api_key → 其余顺序尝试。
        """
        try:
            from app.services.knowledge.provider_registry import (
                ProviderRegistry,
                _load_admin_config,
            )
            from app.services.providers.mock_provider import MockProvider
        except Exception as exc:  # noqa: BLE001
            logger.debug("[Polish] provider imports failed: %s", exc)
            return None

        candidates: List[str] = []
        try:
            llm = _load_admin_config().get("llm", {}) or {}
            models = [
                model for model in (llm.get("models") or [])
                if isinstance(model, dict) and model.get("model")
            ]
            models.sort(key=lambda model: (
                0 if model.get("isDefault")
                else (1 if model.get("api_key") else 2)
            ))
            candidates.extend(str(model["model"]) for model in models)

            # 兼容旧版单模型配置 / 顶层 api_key
            if llm.get("api_key"):
                candidates.append(str(llm.get("model") or "deepseek"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("[Polish] admin config read failed: %s", exc)

        candidates.append("deepseek")  # 环境变量 DEEPSEEK_API_KEY 场景
        candidates.append(str(getattr(settings, "LLM_PROVIDER", "mock")))

        seen: set[str] = set()
        for name in candidates:
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                provider = ProviderRegistry().get_provider(name)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[Polish] get_provider(%s) failed: %s", name, exc)
                continue
            if isinstance(provider, MockProvider):
                continue
            try:
                if not provider.health_check():
                    continue
            except Exception:  # noqa: BLE001
                continue
            logger.info("[Polish] using provider model=%s", name)
            return provider

        logger.warning("[Polish] no usable LLM provider found (falling back to rules)")
        return None

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_llm_output(raw: str) -> str:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    @staticmethod
    def _acceptable(original: str, polished: str) -> bool:
        """一致性校验：长度合理 + 关键型号/数字全部保留。"""
        if not polished or len(polished.strip()) < 20:
            return False

        original_compact = re.sub(r"\s+", "", original or "")
        polished_compact = re.sub(r"\s+", "", polished)
        min_length = max(20, int(len(original_compact) * 0.4))
        if len(polished_compact) < min_length:
            return False

        key_tokens = set(_KEY_TOKEN_RE.findall(original or ""))
        missing = [token for token in key_tokens if token not in polished]
        if missing:
            logger.info("[Polish] LLM output missing key tokens: %s", missing[:10])
            return False
        return True

    @staticmethod
    def _dedupe(items: List[str]) -> List[str]:
        seen: List[str] = []
        for item in items:
            text = (item or "").strip()
            if text and text not in seen:
                seen.append(text)
        return seen
