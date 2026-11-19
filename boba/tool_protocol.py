"""Lesson 02 · 工具协议：每个 tool_use 都要收到一个 tool_result。

三条失败路径——缺参数、未知工具、工具抛异常——都在 ToolRegistry.run
的边界内被转换成 ToolResult，而不是让异常逃出循环。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

ToolFn = Callable[..., Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    tool_use_id: str
    content: dict[str, Any]
    is_error: bool = False


def error_content(code: str, message: str, hint: str) -> dict[str, Any]:
    """错误也是数据：模型要能读懂 code、message 和下一步 hint。"""
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "hint": hint,
        },
    }


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    required: tuple[str, ...]
    properties: tuple[str, ...]
    fn: ToolFn

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        missing = [key for key in self.required if key not in args]
        if missing:
            return error_content(
                "missing_argument",
                f"{self.name} 缺少参数：{', '.join(missing)}",
                "先问顾客缺的那一项，不要自己猜。",
            )

        unknown = [key for key in args if key not in self.properties]
        if unknown:
            return error_content(
                "unknown_argument",
                f"{self.name} 不认识参数：{', '.join(unknown)}",
                "只用工具声明过的参数。",
            )

        try:
            return {"ok": True, "data": self.fn(**args)}
        except Exception as exc:  # 工具边界：把失败变成结果，而不是让循环崩掉
            return error_content(
                "tool_failed",
                f"{self.name} 执行失败：{type(exc).__name__}: {exc}",
                "告诉顾客稍等；需要时换一个只读工具确认状态。",
            )


class ToolRegistry:
    """唯一的工具执行入口。未知工具也在这里变成 tool_result。"""

    def __init__(self, tools: list[Tool] | tuple[Tool, ...] = ()) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def _error(self, call: ToolCall, code: str, message: str, hint: str) -> ToolResult:
        return ToolResult(call.id, error_content(code, message, hint), is_error=True)

    def run(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return self._error(
                call,
                "unknown_tool",
                f"没有注册工具：{call.name}",
                "只调用已注册的工具；不要重复调用不存在的工具。",
            )

        content = tool.run(call.args)
        return ToolResult(call.id, content, is_error=not content["ok"])


MENU: dict[str, dict[str, Any]] = {
    "boba_milk_tea": {"name": "珍珠奶茶", "price": 12},
    "cheese_berry": {"name": "芝士莓莓", "price": 18},
    "four_seasons": {"name": "四季春", "price": 10},
}


def order_create(
    item: str, size: str, ice: str, sugar: str, quantity: int = 1
) -> dict[str, Any]:
    if item not in MENU:
        raise ValueError(f"菜单里没有 {item}")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise ValueError("quantity 必须是正整数")
    menu_item = MENU[item]
    return {
        "order_id": "B1001",
        "item": menu_item["name"],
        "size": size,
        "ice": ice,
        "sugar": sugar,
        "quantity": quantity,
        "total": menu_item["price"] * quantity,
    }


def inventory_check(item: str) -> dict[str, Any]:
    if item == "boba_milk_tea":
        raise RuntimeError("冰箱传感器离线")
    return {"item": item, "cups_left": 20}


def build_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                name="order_create",
                description="创建一杯奶茶订单",
                required=("item", "size", "ice", "sugar"),
                properties=("item", "size", "ice", "sugar", "quantity"),
                fn=order_create,
            ),
            Tool(
                name="inventory_check",
                description="查询某个单品的库存",
                required=("item",),
                properties=("item",),
                fn=inventory_check,
            ),
        ]
    )


def demo() -> list[ToolResult]:
    registry = build_registry()
    calls = [
        ToolCall("call_1", "order_create", {"item": "boba_milk_tea"}),
        ToolCall("call_2", "get_discount", {"order_id": "B1001"}),
        ToolCall("call_3", "inventory_check", {"item": "boba_milk_tea"}),
        ToolCall(
            "call_4",
            "order_create",
            {"item": "boba_milk_tea", "size": "中杯", "ice": "少冰", "sugar": "三分糖"},
        ),
    ]
    return [registry.run(call) for call in calls]
