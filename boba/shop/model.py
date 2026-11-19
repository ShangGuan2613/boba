"""奶茶店领域模型：菜单、选项、库存、订单。

这是 Harness 的第一个“租户”，不是 Harness 的一部分。
所有错误都用 ``ToolError`` 抛出，错误信息会交还给模型。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..core import ToolError
from ..util import utc_now_iso, yuan

__all__ = ["MenuItem", "OptionGroup", "Order", "OrderLine", "Shop"]


def _to_cents(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"金额必须是数字: {value!r}")
    return int(round(float(value) * 100))


@dataclass(frozen=True)
class MenuItem:
    id: str
    name: str
    description: str
    base_price_cents: int
    tags: tuple[str, ...]
    ingredients: dict[str, float]


@dataclass(frozen=True)
class OptionGroup:
    key: str
    label: str
    values: dict[str, str]
    default: str | None = None
    multiple: bool = False
    price_delta_cents: dict[str, int] = field(default_factory=dict)
    ingredients: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class OrderLine:
    item_id: str
    name: str
    qty: int
    options: dict[str, Any]
    unit_price_cents: int
    line_total_cents: int


@dataclass
class Order:
    id: str
    customer: str
    session_id: str
    status: str = "draft"
    lines: list[OrderLine] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    submitted_at: str | None = None
    eta_minutes: int | None = None

    @property
    def cups(self) -> int:
        return sum(line.qty for line in self.lines)

    @property
    def total_cents(self) -> int:
        return sum(line.line_total_cents for line in self.lines)


class Shop:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.name = str(data.get("shop", "波波茶铺"))
        self.currency = str(data.get("currency", "CNY"))
        self.order_prefix = str(data.get("order_prefix", "B"))
        self._next_number = int(data.get("next_order_number", 1001))
        self.large_size_id = str(data.get("large_size_id", "large"))
        self.size_multipliers = {
            str(key): float(value)
            for key, value in dict(data.get("size_multipliers", {})).items()
        }
        self.ingredient_labels = {
            str(key): str(value)
            for key, value in dict(data.get("ingredient_labels", {})).items()
        }

        self.items: dict[str, MenuItem] = {}
        for raw in data.get("items", []):
            item = MenuItem(
                id=str(raw["id"]),
                name=str(raw["name"]),
                description=str(raw.get("description", "")),
                base_price_cents=_to_cents(raw["base_price"]),
                tags=tuple(str(tag) for tag in raw.get("tags", [])),
                ingredients={
                    str(name): float(amount)
                    for name, amount in dict(raw.get("ingredients", {})).items()
                },
            )
            self.items[item.id] = item

        self.options: dict[str, OptionGroup] = {}
        for key, raw in dict(data.get("options", {})).items():
            group = OptionGroup(
                key=str(key),
                label=str(raw.get("label", key)),
                values={
                    str(value): str(label)
                    for value, label in dict(raw.get("values", {})).items()
                },
                default=raw.get("default"),
                multiple=bool(raw.get("multiple", False)),
                price_delta_cents={
                    str(value): _to_cents(delta)
                    for value, delta in dict(raw.get("price_delta", {})).items()
                },
                ingredients={
                    str(value): {
                        str(ingredient): float(amount)
                        for ingredient, amount in dict(amounts).items()
                    }
                    for value, amounts in dict(raw.get("ingredients", {})).items()
                },
            )
            if group.default is not None and group.default not in group.values:
                raise ValueError(f"选项 {group.key} 的默认值 {group.default!r} 不在可选值中")
            for value in group.price_delta_cents:
                if value not in group.values:
                    raise ValueError(f"选项 {group.key} 的加价项 {value!r} 不在可选值中")
            self.options[group.key] = group

        self.inventory: dict[str, float] = {
            str(name): float(amount)
            for name, amount in dict(data.get("inventory", {})).items()
        }
        self._orders: dict[str, Order] = {}
        self._drafts: dict[str, str] = {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Shop":
        source = Path(path) if path is not None else Path(__file__).parent / "data" / "menu.json"
        with source.open("r", encoding="utf-8") as fh:
            return cls(json.load(fh))

    # ---------------------------------------------------------------- 菜单与报价

    def menu_payload(self) -> dict[str, Any]:
        return {
            "shop": self.name,
            "currency": self.currency,
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "base_price": yuan(item.base_price_cents),
                    "tags": list(item.tags),
                }
                for item in self.items.values()
            ],
            "options": {
                key: {
                    "label": group.label,
                    "values": [
                        {
                            "id": value,
                            "label": label,
                            "price_delta": yuan(group.price_delta_cents.get(value, 0)),
                        }
                        for value, label in group.values.items()
                    ],
                    "default": group.default,
                    "multiple": group.multiple,
                }
                for key, group in self.options.items()
            },
        }

    def quote(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        item, qty, options = self._parse_request(arguments)
        unit_cents = self.unit_price_cents(item, options)
        return {
            "item_id": item.id,
            "name": item.name,
            "qty": qty,
            "options": self.option_labels(options),
            "unit_price": yuan(unit_cents),
            "total": yuan(unit_cents * qty),
            "currency": self.currency,
        }

    def check_inventory(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        item, qty, options = self._parse_request(arguments)
        requirements = self._requirements(item, qty, options)
        shortages: list[dict[str, Any]] = []
        for ingredient, needed in sorted(requirements.items()):
            available = self.inventory.get(ingredient, 0.0)
            if needed > available + 1e-9:
                shortages.append(
                    {
                        "ingredient": ingredient,
                        "name": self.ingredient_labels.get(ingredient, ingredient),
                        "needed": round(needed, 2),
                        "available": round(available, 2),
                        "short": round(needed - available, 2),
                    }
                )
        return {
            "item_id": item.id,
            "name": item.name,
            "qty": qty,
            "available": not shortages,
            "shortages": shortages,
            "currency": self.currency,
        }

    # ---------------------------------------------------------------- 订单

    def create_order(self, session_id: str, customer: str = "散客") -> dict[str, Any]:
        customer = customer.strip() or "散客"
        existing_order = self.resolve_order(session_id)
        if existing_order is not None and existing_order.status == "draft":
            if customer != "散客":
                existing_order.customer = customer
            return {
                "order_id": existing_order.id,
                "customer": existing_order.customer,
                "status": existing_order.status,
                "cups": existing_order.cups,
                "total": yuan(existing_order.total_cents),
                "currency": self.currency,
                "existing": True,
            }

        order = Order(
            id=self._new_order_id(),
            customer=customer,
            session_id=session_id,
        )
        self._orders[order.id] = order
        self._drafts[session_id] = order.id
        return {
            "order_id": order.id,
            "customer": order.customer,
            "status": order.status,
            "cups": order.cups,
            "total": yuan(order.total_cents),
            "currency": self.currency,
            "existing": False,
        }

    def add_item(
        self, session_id: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        allowed = {"item_id", "qty", "order_id"} | set(self.options)
        item, qty, options = self._parse_request(arguments, allowed=allowed)

        order = self.resolve_order(session_id, arguments.get("order_id"))
        if order is None:
            self.create_order(session_id)
            order = self.resolve_order(session_id)
            assert order is not None
        if order.status != "draft":
            raise ToolError(f"订单 {order.id} 已提交，不能再加单")
        self._require_owner(order, session_id)

        unit_cents = self.unit_price_cents(item, options)
        line = OrderLine(
            item_id=item.id,
            name=item.name,
            qty=qty,
            options=options,
            unit_price_cents=unit_cents,
            line_total_cents=unit_cents * qty,
        )
        order.lines.append(line)
        return {
            "order_id": order.id,
            "line": self.line_payload(line, item),
            "cups": order.cups,
            "total": yuan(order.total_cents),
            "currency": self.currency,
            "status": order.status,
        }

    def submit(self, session_id: str, order_id: str | None = None) -> dict[str, Any]:
        order = self.resolve_order(session_id, order_id)
        if order is None:
            raise ToolError("当前会话还没有订单，请先加饮品")
        self._require_owner(order, session_id)
        if order.status == "submitted":
            payload = self.order_payload(order)
            payload["already_submitted"] = True
            return payload
        if not order.lines:
            raise ToolError("订单是空的，请先加饮品")

        requirements = self._order_requirements(order)
        shortages = [
            {
                "ingredient": ingredient,
                "name": self.ingredient_labels.get(ingredient, ingredient),
                "needed": round(needed, 2),
                "available": round(self.inventory.get(ingredient, 0.0), 2),
                "short": round(needed - self.inventory.get(ingredient, 0.0), 2),
            }
            for ingredient, needed in sorted(requirements.items())
            if needed > self.inventory.get(ingredient, 0.0) + 1e-9
        ]
        if shortages:
            detail = "；".join(
                f"{item['name']}差 {item['short']}" for item in shortages
            )
            raise ToolError(f"原料不够，无法提交：{detail}")

        for ingredient, needed in requirements.items():
            self.inventory[ingredient] = round(
                self.inventory.get(ingredient, 0.0) - needed, 2
            )

        order.status = "submitted"
        order.submitted_at = utc_now_iso()
        order.eta_minutes = round(3 + 1.5 * order.cups)
        self._drafts.pop(order.session_id, None)
        return self.order_payload(order)

    def status(self, session_id: str, order_id: str | None = None) -> dict[str, Any]:
        order = self.resolve_order(session_id, order_id)
        if order is None:
            raise ToolError("当前会话还没有订单")
        self._require_owner(order, session_id)
        return self.order_payload(order)

    def resolve_order(
        self, session_id: str, order_id: str | None = None
    ) -> Order | None:
        if order_id is not None:
            if not isinstance(order_id, str):
                raise ToolError("order_id 必须是字符串")
            order = self._orders.get(order_id)
            if order is None:
                raise ToolError(f"找不到订单 {order_id!r}")
            return order
        draft_id = self._drafts.get(session_id)
        if draft_id is None:
            return None
        return self._orders.get(draft_id)

    def peek_draft(
        self, session_id: str, order_id: str | None = None
    ) -> Order | None:
        """给护栏用的无异常查询：订单不存在时返回 None。"""
        if order_id is not None and not isinstance(order_id, str):
            return None
        try:
            return self.resolve_order(session_id, order_id)
        except ToolError:
            return None

    def last_order(self) -> Order | None:
        if not self._orders:
            return None
        return next(reversed(self._orders.values()))

    # ---------------------------------------------------------------- 展示

    def option_labels(self, options: Mapping[str, Any]) -> dict[str, Any]:
        labels: dict[str, Any] = {}
        for key, group in self.options.items():
            value = options.get(key, group.default)
            if group.multiple:
                values = value or []
                labels[key] = [group.values.get(item, str(item)) for item in values]
            elif value is not None:
                labels[key] = group.values.get(value, str(value))
        return labels

    def describe_line(self, line: OrderLine) -> str:
        labels: list[str] = []
        for key in ("size", "ice", "sugar"):
            group = self.options.get(key)
            value = line.options.get(key)
            if group is not None and value is not None:
                labels.append(group.values.get(value, str(value)))
        for key, group in self.options.items():
            if not group.multiple:
                continue
            values = line.options.get(key) or []
            if values:
                labels.append(
                    "加" + "、".join(group.values.get(value, str(value)) for value in values)
                )
        suffix = f"（{' / '.join(labels)}）" if labels else ""
        return f"{line.name} ×{line.qty}{suffix}"

    def line_payload(
        self, line: OrderLine, item: MenuItem | None = None
    ) -> dict[str, Any]:
        item = item or self.items[line.item_id]
        return {
            "item_id": line.item_id,
            "name": line.name,
            "qty": line.qty,
            "options": self.option_labels(line.options),
            "unit_price": yuan(line.unit_price_cents),
            "line_total": yuan(line.line_total_cents),
        }

    def order_payload(self, order: Order) -> dict[str, Any]:
        return {
            "order_id": order.id,
            "customer": order.customer,
            "status": order.status,
            "lines": [self.line_payload(line) for line in order.lines],
            "cups": order.cups,
            "total": yuan(order.total_cents),
            "currency": self.currency,
            "eta_minutes": order.eta_minutes,
            "created_at": order.created_at,
            "submitted_at": order.submitted_at,
        }

    # ---------------------------------------------------------------- 内部

    def _parse_request(
        self,
        arguments: Mapping[str, Any],
        *,
        allowed: set[str] | None = None,
    ) -> tuple[MenuItem, int, dict[str, Any]]:
        allowed = {"item_id", "qty"} | set(self.options) if allowed is None else allowed
        unknown = sorted(set(arguments) - allowed)
        if unknown:
            raise ToolError(
                f"不支持的参数：{', '.join(unknown)}；可用参数：{', '.join(sorted(allowed))}"
            )

        item_id = arguments.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise ToolError("缺少 item_id，请先看菜单")
        item = self.items.get(item_id)
        if item is None:
            raise ToolError(
                f"菜单上没有 {item_id!r}；可选：{', '.join(self.items)}"
            )

        qty = self._parse_qty(arguments.get("qty", 1))
        raw_options = {
            key: arguments[key] for key in self.options if key in arguments
        }
        options = self.normalize_options(raw_options)
        return item, qty, options

    @staticmethod
    def _parse_qty(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolError("qty 必须是整数（杯数）")
        if not 1 <= value <= 99:
            raise ToolError("qty 需在 1 到 99 之间")
        return value

    def normalize_options(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(raw) - set(self.options))
        if unknown:
            raise ToolError(
                f"未知选项：{', '.join(unknown)}；可选项：{', '.join(self.options)}"
            )

        options: dict[str, Any] = {}
        for key, group in self.options.items():
            value = raw.get(key, group.default)
            if group.multiple:
                if value is None:
                    value = []
                if isinstance(value, str):
                    value = [value]
                if not isinstance(value, list):
                    raise ToolError(f"{group.label}必须是数组")
                normalized: list[str] = []
                for entry in value:
                    if not isinstance(entry, str) or entry not in group.values:
                        raise ToolError(
                            f"{group.label}只支持：{', '.join(group.values)}"
                        )
                    if entry not in normalized:
                        normalized.append(entry)
                options[key] = normalized
            else:
                if value not in group.values:
                    raise ToolError(
                        f"{group.label}只支持：{', '.join(group.values)}（收到 {value!r}）"
                    )
                options[key] = value
        return options

    def unit_price_cents(
        self, item: MenuItem, options: Mapping[str, Any]
    ) -> int:
        cents = item.base_price_cents
        for key, group in self.options.items():
            value = options.get(key)
            if group.multiple:
                for entry in value or []:
                    cents += group.price_delta_cents.get(entry, 0)
            elif value is not None:
                cents += group.price_delta_cents.get(value, 0)
        return cents

    def _requirements(
        self,
        item: MenuItem,
        qty: int,
        options: Mapping[str, Any],
    ) -> dict[str, float]:
        size = options.get("size")
        factor = self.size_multipliers.get(size, 1.0) if size else 1.0
        requirements = {
            ingredient: amount * factor * qty
            for ingredient, amount in item.ingredients.items()
        }
        for key, group in self.options.items():
            if not group.multiple:
                continue
            for entry in options.get(key) or []:
                for ingredient, amount in group.ingredients.get(entry, {}).items():
                    requirements[ingredient] = (
                        requirements.get(ingredient, 0.0) + amount * qty
                    )
        return {
            ingredient: round(amount, 2)
            for ingredient, amount in requirements.items()
        }

    def _order_requirements(self, order: Order) -> dict[str, float]:
        requirements: dict[str, float] = {}
        for line in order.lines:
            item = self.items[line.item_id]
            for ingredient, amount in self._requirements(
                item, line.qty, line.options
            ).items():
                requirements[ingredient] = (
                    requirements.get(ingredient, 0.0) + amount
                )
        return {
            ingredient: round(amount, 2)
            for ingredient, amount in requirements.items()
        }

    def _new_order_id(self) -> str:
        order_id = f"{self.order_prefix}{self._next_number}"
        self._next_number += 1
        return order_id

    @staticmethod
    def _require_owner(order: Order, session_id: str) -> None:
        if order.session_id != session_id:
            raise ToolError(f"订单 {order.id} 不属于当前会话")
