"""Lesson 05 · 小票与订单夹：状态 / session。

单笔护栏只看手里的单子；订单夹看的是这一桌从坐下到现在
一共点了多少。状态由 harness 持有，模型看不见，也不能直接改。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from boba.guardrails import (
    ALLOW,
    GuardrailDecision,
    GuardrailRegistry,
    run_guarded,
)
from boba.tool_protocol import ToolCall, ToolRegistry, ToolResult, build_registry


@dataclass
class SessionState:
    """一桌顾客的订单夹。只有这个 session 能看见里面有什么。"""

    id: str
    orders: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_cups(self) -> int:
        return sum(order["quantity"] for order in self.orders)

    def add_order(self, order_id: str, quantity: int) -> None:
        self.orders.append(
            {"order_id": order_id, "quantity": quantity, "status": "draft"}
        )

    def find_order(self, order_id: str) -> dict[str, Any] | None:
        return next(
            (order for order in self.orders if order["order_id"] == order_id),
            None,
        )


class SessionStore:
    """按桌号取订单夹。没见过的桌号先开一本空的。"""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id)
        return self._sessions[session_id]


class MaxCupsPerSession:
    """整段会话最多 N 杯。看“订单夹已有 + 本次”，而不是只看本次。"""

    name = "max_cups_per_session"

    def __init__(self, limit: int = 10) -> None:
        self.limit = limit

    def check(self, call: ToolCall, session: Any = None) -> GuardrailDecision:
        if call.name != "order_create":
            return ALLOW

        if session is None:
            return GuardrailDecision(
                False,
                "guardrail_error",
                "缺少 session，无法检查会话总量。",
                "默认拒绝；检查护栏接线时有没有把 session 传进来。",
            )

        total = getattr(session, "total_cups", None)
        if not isinstance(total, int):
            return GuardrailDecision(
                False,
                "guardrail_error",
                "session 缺少 total_cups，无法检查会话总量。",
                "默认拒绝；检查状态对象是否接错。",
            )

        quantity = call.args.get("quantity", 1)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            return GuardrailDecision(
                False,
                "invalid_quantity",
                f"数量必须是正整数，收到 {quantity!r}。",
                "先向顾客确认数量。",
            )

        if total + quantity > self.limit:
            return GuardrailDecision(
                False,
                "permission_denied",
                f"本次会话最多 {self.limit} 杯，已有 {total} 杯，"
                f"再加 {quantity} 杯会超。",
                "不要拆单；向顾客解释店规，必要时转人工。",
            )

        return ALLOW


def place_order(
    session: SessionState,
    call: ToolCall,
    tools: ToolRegistry,
    guardrails: GuardrailRegistry,
) -> ToolResult:
    """护栏放行、工具成功之后，才把这张单记进订单夹。"""
    result = run_guarded(call, tools, guardrails, session)
    if not result.is_error:
        data = result.content["data"]
        session.add_order(data["order_id"], data["quantity"])
    return result


def demo() -> None:
    tools = build_registry()
    guardrails = GuardrailRegistry([MaxCupsPerSession(10)])
    session = SessionState("table-3")

    for index, quantity in enumerate((10, 10), start=1):
        call = ToolCall(
            f"call_{index}",
            "order_create",
            {
                "item": "boba_milk_tea",
                "size": "中杯",
                "ice": "少冰",
                "sugar": "三分糖",
                "quantity": quantity,
            },
        )
        result = place_order(session, call, tools, guardrails)
        if result.is_error:
            code = result.content["error"]["code"]
            print(f"{quantity:>2} 杯 → {code}；订单夹合计仍是 {session.total_cups} 杯")
        else:
            print(f"{quantity:>2} 杯 → ok；订单夹合计 {session.total_cups} 杯")


if __name__ == "__main__":
    demo()
