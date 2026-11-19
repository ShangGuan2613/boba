"""离线演示：一位顾客、两杯珍珠奶茶、一张真实小票。

不需要 API key，也不需要安装第三方依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .barista import build_barista
from .core import ModelTurn, call, say, text_block, tool_use_block, turn
from .harness import Harness, HarnessConfig, RunResult, Session
from .models import ScriptedModel
from .shop import MaxCupsPerOrder, Order, Shop
from .util import money

__all__ = ["DEMO_USER_MESSAGE", "DemoRun", "run_demo"]

DEMO_USER_MESSAGE = "你好，我要两杯珍珠奶茶：一杯少冰半糖，一杯正常冰全糖。"


@dataclass
class DemoRun:
    result: RunResult
    shop: Shop
    order: Order | None


def run_demo(
    *,
    trace_dir: str | Path | None = "traces",
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> DemoRun:
    shop = Shop.load()
    agent = build_barista(shop)

    def final_reply(messages: list[dict[str, Any]]) -> ModelTurn:
        order = shop.last_order()
        if order is None or order.status != "submitted":
            return say("这单还没走完，我再确认一下～")
        lines = "、".join(shop.describe_line(line) for line in order.lines)
        return say(
            f"搞定啦，{order.customer}！订单 {order.id}：{lines}，"
            f"共 {money(order.total_cents)}，预计 {order.eta_minutes} 分钟后叫号取茶。🍵"
        )

    script = [
        turn(
            text_block("好嘞，我先看下今天的菜单，再帮你确认原料够不够～"),
            tool_use_block("menu_list"),
        ),
        call("inventory_check", item_id="boba_milk_tea", qty=2),
        call("order_create", customer="阿珍"),
        call(
            "order_add_item",
            item_id="boba_milk_tea",
            qty=1,
            ice="less",
            sugar="half",
        ),
        call(
            "order_add_item",
            item_id="boba_milk_tea",
            qty=1,
            ice="normal",
            sugar="full",
        ),
        call("order_submit"),
        final_reply,
    ]

    trace_enabled = trace_dir is not None
    harness = Harness(
        agent=agent,
        model=ScriptedModel(script),
        config=HarnessConfig(
            trace=trace_enabled,
            trace_dir=Path(trace_dir) if trace_enabled else None,
        ),
        resources={"shop": shop},
        guardrails=[MaxCupsPerOrder(10)],
        on_event=on_event,
    )
    result = harness.run(DEMO_USER_MESSAGE, session=Session())
    return DemoRun(result=result, shop=shop, order=shop.last_order())
