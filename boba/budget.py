"""Lesson 03 · 打烊铃：预算与超时。

预算不是提示词里的“请尽快”，而是循环里的硬检查：
- max_turns：最多几轮模型调用
- max_tool_calls：最多几次工具执行
- max_seconds：最多让顾客等多久

检查发生在“花钱之前”：先看额度，再决定要不要做。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from boba.tool_protocol import ToolCall, ToolResult, error_content


class BudgetExceeded(Exception):
    """预算耗尽。它由 Harness 捕获，变成一次带状态的收尾，不逃到用户面前。"""

    def __init__(self, status: str, user_message: str, detail: str = "") -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.user_message = user_message
        self.detail = detail


@dataclass
class Budget:
    max_turns: int = 8
    max_tool_calls: int = 16
    max_seconds: float = 60.0
    clock: Callable[[], float] = time.monotonic
    turns: int = 0
    tool_calls: int = 0
    started_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    @property
    def elapsed(self) -> float:
        return self.clock() - self.started_at

    def _check_timeout(self) -> None:
        if self.elapsed >= self.max_seconds:
            raise BudgetExceeded(
                "timeout",
                "现在排队比较久，我先帮您留单，稍后再试。",
                f"elapsed={self.elapsed:.1f}s",
            )

    def start_turn(self) -> None:
        """模型调用前先扣一轮。轮数闸门只管模型调用。"""
        self._check_timeout()
        if self.turns >= self.max_turns:
            raise BudgetExceeded(
                "max_turns",
                "今天先聊到这里，您要的我都记下了，稍后人工同事跟进。",
                f"turns={self.turns}",
            )
        self.turns += 1

    def start_tool(self) -> None:
        """工具执行前先扣一次。工具闸门只管工具执行。"""
        self._check_timeout()
        if self.tool_calls >= self.max_tool_calls:
            raise BudgetExceeded(
                "max_tool_calls",
                "今天先做到这里，您这杯已经排上，稍后确认。",
                f"tool_calls={self.tool_calls}",
            )
        self.tool_calls += 1

    def snapshot(self) -> dict[str, float | int]:
        return {
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "elapsed": round(self.elapsed, 2),
        }


def budget_error_result(call: ToolCall, status: str) -> ToolResult:
    """铃响时，给还没执行的 tool_use 补一张退单小票。"""
    return ToolResult(
        call.id,
        error_content(
            "budget_exhausted",
            f"{status} 已用完",
            "停止并交接，不要继续试。",
        ),
        is_error=True,
    )


def demo() -> None:
    budget = Budget(max_turns=4, max_tool_calls=3, max_seconds=30)
    for i in range(1, 6):
        try:
            budget.start_turn()
            budget.start_tool()
            print(f"第 {i} 轮：做。已用 {budget.snapshot()}")
        except BudgetExceeded as stop:
            print(f"第 {i} 轮：叮！{stop.status}——{stop.user_message}")
            print(f"最终用量：{budget.snapshot()}")
            break


if __name__ == "__main__":
    demo()
