"""Lesson 04 · 店规：护栏。

预算管“做多少”，护栏管“能不能做”。
护栏是代码级否决：在工具执行之前检查，拒绝时回一张
permission_denied 小票，模型只能解释，不能绕过。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from boba.tool_protocol import ToolCall, ToolRegistry, ToolResult, error_content


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    code: str = ""
    message: str = ""
    hint: str = ""


ALLOW = GuardrailDecision(True)


class Guardrail(Protocol):
    name: str

    def check(self, call: ToolCall, session: Any = None) -> GuardrailDecision:
        ...


class MaxCupsPerOrder:
    """单笔最多 N 杯。只拦 order_create，不碰其他工具。"""

    name = "max_cups_per_order"

    def __init__(self, limit: int = 10) -> None:
        self.limit = limit

    def check(self, call: ToolCall, session: Any = None) -> GuardrailDecision:
        if call.name != "order_create":
            return ALLOW

        quantity = call.args.get("quantity", 1)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            return GuardrailDecision(
                False,
                "invalid_quantity",
                f"数量必须是正整数，收到 {quantity!r}。",
                "先向顾客确认数量。",
            )

        if quantity > self.limit:
            return GuardrailDecision(
                False,
                "permission_denied",
                f"单笔最多 {self.limit} 杯，这次是 {quantity} 杯。",
                "不要自动拆单绕过；先向顾客解释店规，必要时转人工。",
            )

        return ALLOW


class GuardrailRegistry:
    """按顺序检查；第一条拒绝生效。护栏自己坏了，默认拒绝。"""

    def __init__(self, guardrails: list[Guardrail] | None = None) -> None:
        self._guardrails = list(guardrails or [])

    def check(self, call: ToolCall, session: Any = None) -> GuardrailDecision:
        for guardrail in self._guardrails:
            try:
                decision = guardrail.check(call, session)
            except Exception as exc:  # 失败关闭：护栏坏了，不能放行
                return GuardrailDecision(
                    False,
                    "guardrail_error",
                    f"护栏 {getattr(guardrail, 'name', '?')} 执行失败：{exc}",
                    "默认拒绝；请转人工。",
                )
            if not decision.allowed:
                return decision
        return ALLOW


def denied_result(call: ToolCall, decision: GuardrailDecision) -> ToolResult:
    return ToolResult(
        call.id,
        error_content(decision.code, decision.message, decision.hint),
        is_error=True,
    )


def run_guarded(
    call: ToolCall,
    tools: ToolRegistry,
    guardrails: GuardrailRegistry,
    session: Any = None,
) -> ToolResult:
    """先过店规，再让工具动手。被拒绝时工具一次都不会执行。"""
    decision = guardrails.check(call, session)
    if not decision.allowed:
        return denied_result(call, decision)
    return tools.run(call)


def demo() -> None:
    from boba.tool_protocol import build_registry

    tools = build_registry()
    guardrails = GuardrailRegistry([MaxCupsPerOrder(10)])

    for quantity in (5, 10, 11, 20):
        call = ToolCall(
            f"call_{quantity}",
            "order_create",
            {
                "item": "boba_milk_tea",
                "size": "中杯",
                "ice": "少冰",
                "sugar": "三分糖",
                "quantity": quantity,
            },
        )
        result = run_guarded(call, tools, guardrails)
        status = result.content["error"]["code"] if result.is_error else "ok"
        print(f"{quantity:>2} 杯 → {status}")


if __name__ == "__main__":
    demo()
