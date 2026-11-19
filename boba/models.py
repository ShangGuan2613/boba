"""两种茶底/原料：

- ScriptedModel：离线、确定性的脚本模型，用于 demo 和测试；
- AnthropicModel：真实 Claude 适配器（可选依赖 ``anthropic``）。

两者都遵守 ``boba.core.Model`` 协议，Harness 不需要知道区别。
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Sequence

from .core import Model, ModelTurn, Tool, say

__all__ = ["AnthropicModel", "ScriptedModel", "DEFAULT_MODEL"]

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_FALLBACK_MODEL = "claude-opus-4-8"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}


class ScriptedModel:
    """按预设脚本逐回合回复的模型。

    脚本元素可以是 ``ModelTurn``，也可以是 ``callable(messages) -> ModelTurn``。
    后者能读到当前会话，适合在演示结尾根据工具结果生成小票文案。

    注意：这是测试替身，不是“假 AI”。它不会根据输入推理。
    """

    name = "scripted"
    label = "scripted"

    def __init__(
        self,
        script: Sequence[ModelTurn | Callable[[list[dict[str, Any]]], ModelTurn]],
        *,
        fallback_text: str = "（脚本演完了：没有更多预设回合）",
    ) -> None:
        self._script = list(script)
        self._index = 0
        self._counter = itertools.count(1)
        self._fallback_text = fallback_text

    def generate(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[Tool],
    ) -> ModelTurn:
        if self._index >= len(self._script):
            return say(self._fallback_text)

        step = self._script[self._index]
        self._index += 1
        model_turn = step(list(messages)) if callable(step) else step

        content: list[dict[str, Any]] = []
        for block in model_turn.content:
            block = dict(block)
            if block.get("type") == "tool_use" and not block.get("id"):
                block["id"] = f"call_{next(self._counter)}"
            content.append(block)
        return ModelTurn(content=content, stop_reason=model_turn.stop_reason)


class AnthropicModel:
    """Claude Messages API 适配器。

    默认 model 为 ``claude-opus-5-5``，开启 adaptive thinking，默认 effort 为
    ``medium``（该模型的默认值，显式写出以免随版本漂移）。默认启用服务端
    refusal fallback；如不需要可传 ``fallbacks=False``。

    安装：``pip install 'boba[anthropic]'``，然后配置 ANTHROPIC_API_KEY。
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 16000,
        effort: str = "medium",
        fallbacks: bool = True,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
        client: Any | None = None,
    ) -> None:
        if effort not in EFFORT_LEVELS:
            raise ValueError(f"effort 必须是 {sorted(EFFORT_LEVELS)} 之一")
        if max_tokens < 1:
            raise ValueError("max_tokens 必须 >= 1")

        if client is None:
            try:
                import anthropic  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "AnthropicModel 需要可选依赖：pip install 'boba[anthropic]'"
                ) from exc
            client = anthropic.Anthropic()

        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.fallbacks = fallbacks
        self.fallback_model = fallback_model
        self._client = client

    @property
    def label(self) -> str:
        return f"anthropic:{self.model}"

    def generate(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[Tool],
    ) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": list(messages),
            "tools": [tool.spec() for tool in tools],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
        }

        response = None
        if self.fallbacks and hasattr(self._client, "beta"):
            try:
                response = self._client.beta.messages.create(
                    **kwargs,
                    betas=[FALLBACK_BETA],
                    fallbacks=[{"model": self.fallback_model}],
                )
            except TypeError:
                # 旧版 SDK 不认识 beta/fallbacks 参数：退回到标准 Messages API。
                response = None

        if response is None:
            response = self._client.messages.create(**kwargs)

        stop_reason = getattr(response, "stop_reason", None) or "end_turn"
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            note = "抱歉，这个请求我无法处理。"
            if category:
                note += f"（类别：{category}）"
            return ModelTurn(
                content=[{"type": "text", "text": note}], stop_reason="refusal"
            )

        content = _normalize_content(getattr(response, "content", []) or [])
        if not content:
            content = [{"type": "text", "text": "（模型没有返回内容）"}]
        return ModelTurn(content=content, stop_reason=stop_reason)


def _normalize_content(blocks: Sequence[Any]) -> list[dict[str, Any]]:
    """把 SDK 的 content block 转成可回放的普通 dict。

    只保留能安全回传的四种块；fallback 等信号块不进入会话历史。
    """
    normalized: list[dict[str, Any]] = []
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            normalized.append({"type": "text", "text": getattr(block, "text", "")})
        elif block_type == "thinking":
            normalized.append(
                {
                    "type": "thinking",
                    "thinking": getattr(block, "thinking", ""),
                    "signature": getattr(block, "signature", ""),
                }
            )
        elif block_type == "redacted_thinking":
            normalized.append(
                {"type": "redacted_thinking", "data": getattr(block, "data", "")}
            )
        elif block_type == "tool_use":
            normalized.append(
                {
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": dict(getattr(block, "input", {}) or {}),
                }
            )
    return normalized
