"""店长守则（Guardrail）：Harness 和具体店铺之间的第一道人工规则。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core import Tool, ToolContext

__all__ = ["MaxCupsPerOrder"]


@dataclass(frozen=True)
class MaxCupsPerOrder:
    """单笔订单最多 N 杯。只拦截加单，不拦查看类工具。"""

    limit: int = 10

    def check(
        self, *, tool: Tool, arguments: dict[str, Any], ctx: ToolContext
    ) -> str | None:
        if tool.name != "order_add_item":
            return None
        qty = arguments.get("qty", 1)
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            return None  # 让工具自己给出参数错误
        shop = ctx.resource("shop")
        order = shop.peek_draft(ctx.session_id, arguments.get("order_id"))
        current = order.cups if order is not None else 0
        if current + qty > self.limit:
            return (
                f"店长守则：单笔订单最多 {self.limit} 杯"
                f"（已有 {current} 杯，本次 {qty} 杯）"
            )
        return None
