"""把奶茶店的操作包装成模型可调用的工具（设备/工位）。"""

from __future__ import annotations

from typing import Any, Callable

from ..core import Tool, ToolContext, ToolError
from .model import Shop

__all__ = ["build_tools"]

Handler = Callable[[ToolContext, dict[str, Any]], Any]


def _check_unknown(
    arguments: dict[str, Any], allowed: set[str], tool_name: str
) -> None:
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        raise ToolError(
            f"{tool_name} 不支持参数：{', '.join(unknown)}；"
            f"可用参数：{', '.join(sorted(allowed))}"
        )


def _schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _option_properties(shop: Shop) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for key, group in shop.options.items():
        if group.multiple:
            properties[key] = {
                "type": "array",
                "items": {"type": "string", "enum": list(group.values)},
                "uniqueItems": True,
                "description": f"{group.label}，可多选，可为空",
            }
        else:
            prop: dict[str, Any] = {
                "type": "string",
                "enum": list(group.values),
                "description": group.label,
            }
            if group.default is not None:
                prop["default"] = group.default
            properties[key] = prop
    return properties


def build_tools(shop: Shop) -> list[Tool]:
    item_schema = {
        "type": "string",
        "enum": list(shop.items),
        "description": "菜单商品 id；先调用 menu_list 确认",
    }
    qty_schema = {
        "type": "integer",
        "minimum": 1,
        "maximum": 99,
        "default": 1,
        "description": "杯数",
    }
    order_id_schema = {
        "type": "string",
        "description": "订单号；省略时使用当前会话的草稿单",
    }
    option_props = _option_properties(shop)

    def menu_list(ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        _check_unknown(arguments, set(), "menu_list")
        return shop.menu_payload()

    def menu_price(ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        return shop.quote(arguments)

    def inventory_check(ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        return shop.check_inventory(arguments)

    def order_create(ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        _check_unknown(arguments, {"customer"}, "order_create")
        customer = arguments.get("customer", "散客")
        if not isinstance(customer, str):
            raise ToolError("customer 必须是字符串")
        customer = customer.strip()
        if len(customer) > 40:
            raise ToolError("customer 最长 40 个字符")
        return shop.create_order(ctx.session_id, customer or "散客")

    def order_add_item(ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        return shop.add_item(ctx.session_id, arguments)

    def order_submit(ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        _check_unknown(arguments, {"order_id"}, "order_submit")
        order_id = arguments.get("order_id")
        if order_id is not None and not isinstance(order_id, str):
            raise ToolError("order_id 必须是字符串")
        return shop.submit(ctx.session_id, order_id)

    def order_status(ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        _check_unknown(arguments, {"order_id"}, "order_status")
        order_id = arguments.get("order_id")
        if order_id is not None and not isinstance(order_id, str):
            raise ToolError("order_id 必须是字符串")
        return shop.status(ctx.session_id, order_id)

    return [
        Tool(
            name="menu_list",
            description=(
                "查看今日菜单：饮品、价格、杯型/冰度/糖度/小料选项。"
                "接待顾客或报价前先调用，不要凭记忆编价格。"
            ),
            input_schema=_schema(),
            handler=menu_list,
            label="看菜单",
        ),
        Tool(
            name="menu_price",
            description="按真实菜单计算一杯或指定杯数的价格，不写入订单。",
            input_schema=_schema(
                {
                    "item_id": item_schema,
                    "qty": qty_schema,
                    **option_props,
                },
                required=["item_id"],
            ),
            handler=menu_price,
            label="报价",
        ),
        Tool(
            name="inventory_check",
            description="检查某款饮品在指定杯数下原料是否够用，不扣库存。",
            input_schema=_schema(
                {
                    "item_id": item_schema,
                    "qty": qty_schema,
                    **option_props,
                },
                required=["item_id"],
            ),
            handler=inventory_check,
            label="查库存",
        ),
        Tool(
            name="order_create",
            description=(
                "为当前会话开一张草稿订单；已有草稿单时直接复用。"
                "也可以省略，order_add_item 会自动开单。"
            ),
            input_schema=_schema(
                {
                    "customer": {
                        "type": "string",
                        "maxLength": 40,
                        "description": "顾客称呼，默认「散客」",
                    }
                }
            ),
            handler=order_create,
            label="开单",
        ),
        Tool(
            name="order_add_item",
            description=(
                "往草稿订单加饮品；不传 order_id 时自动使用当前会话的草稿单。"
                "qty 可一次加多杯，但受「单笔最多 10 杯」的店长守则限制。"
            ),
            input_schema=_schema(
                {
                    "item_id": item_schema,
                    "qty": qty_schema,
                    **option_props,
                    "order_id": order_id_schema,
                },
                required=["item_id"],
            ),
            handler=order_add_item,
            label="加饮品",
        ),
        Tool(
            name="order_submit",
            description=(
                "提交草稿订单：校验并扣减库存，返回小票"
                "（订单号、品项、总价、预计等待时间）。"
            ),
            input_schema=_schema({"order_id": order_id_schema}),
            handler=order_submit,
            label="提交订单",
        ),
        Tool(
            name="order_status",
            description="查询订单状态与小票信息；不传 order_id 时查当前会话的订单。",
            input_schema=_schema({"order_id": order_id_schema}),
            handler=order_status,
            label="查订单",
        ),
    ]
