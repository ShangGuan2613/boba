"""命令行入口：demo / chat / trace / menu。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import __version__
from .barista import build_barista
from .demo import DEMO_USER_MESSAGE, run_demo
from .harness import Harness, HarnessConfig, Session
from .models import AnthropicModel, DEFAULT_MODEL, EFFORT_LEVELS
from .shop import MaxCupsPerOrder, Shop
from .trace import load_events, render_events
from .util import clip, money

__all__ = ["main"]


def _amount(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            return f"¥{int(value)}"
        return f"¥{value:.2f}"
    return str(value)


def _summarize_tool(name: str, result: Any) -> str:
    if not isinstance(result, dict):
        return clip(result, 90)
    if name == "menu_list":
        return f"{result.get('shop', '')} · {len(result.get('items', []))} 款饮品"
    if name == "menu_price":
        return (
            f"{result.get('name')} ×{result.get('qty')} · "
            f"单价 {_amount(result.get('unit_price'))} · 合计 {_amount(result.get('total'))}"
        )
    if name == "inventory_check":
        if result.get("available"):
            return f"{result.get('name')} ×{result.get('qty')} · 原料充足"
        shortages = "；".join(
            f"{item.get('name')} 差 {item.get('short')}"
            for item in result.get("shortages", [])
        )
        return f"缺料：{shortages}"
    if name == "order_create":
        suffix = "（复用草稿）" if result.get("existing") else ""
        return f"开单 {result.get('order_id')} · {result.get('customer')}{suffix}"
    if name == "order_add_item":
        line = result.get("line") or {}
        return (
            f"{line.get('name')} ×{line.get('qty')} · "
            f"订单共 {_amount(result.get('total'))}"
        )
    if name == "order_submit":
        suffix = "（已提交过）" if result.get("already_submitted") else ""
        return (
            f"{result.get('order_id')} 已提交 · {_amount(result.get('total'))} · "
            f"约 {result.get('eta_minutes')} 分钟{suffix}"
        )
    if name == "order_status":
        return (
            f"{result.get('order_id')} · {result.get('status')} · "
            f"{_amount(result.get('total'))}"
        )
    return clip(json.dumps(result, ensure_ascii=False), 90)


class EventPrinter:
    """把 Harness 的小票事件实时打印成门店对话。"""

    def __call__(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        data = event.get("data") or {}

        if event_type == "model.response":
            text = data.get("text") or ""
            if text:
                print(f"🧑‍🍳 小波：{text}")
        elif event_type == "tool.call":
            arguments = json.dumps(data.get("arguments") or {}, ensure_ascii=False)
            print(f"   🔧 {data.get('tool')}({clip(arguments, 72)})")
        elif event_type == "tool.result":
            if data.get("ok"):
                print(
                    f"      ↳ {_summarize_tool(data.get('tool', ''), data.get('result'))}"
                )
            else:
                print(f"      ↳ ⚠️ {clip(data.get('error', ''), 110)}")
        elif event_type == "tool.skipped":
            print(f"   ⏭️ 跳过 {data.get('tool')}：{data.get('reason')}")
        elif event_type == "guardrail.denied":
            print(f"   🛑 店长拦下：{data.get('reason')}")
        elif event_type == "harness.stopped":
            print(f"   ⏹️ 停止：{data.get('reason')}")
        elif event_type in {"model.error", "tool.error", "harness.error"}:
            print(f"   ❌ {event_type}: {clip(data.get('error', ''), 120)}")


def _print_menu(shop: Shop) -> None:
    print(f"🍵 {shop.name} · {shop.currency}")
    for item in shop.items.values():
        tags = " / ".join(item.tags)
        print(
            f"  {item.name:<7} {money(item.base_price_cents):>6}  "
            f"{tags} — {item.description}"
        )
    for group in shop.options.values():
        values = " / ".join(
            f"{label}"
            + (
                f"(+{money(group.price_delta_cents[value])})"
                if group.price_delta_cents.get(value)
                else ""
            )
            for value, label in group.values.items()
        )
        multiple = "（可多选）" if group.multiple else ""
        print(f"  {group.label}：{values}{multiple}")


def cmd_demo(args: argparse.Namespace) -> int:
    trace_dir = None if args.no_trace else args.trace_dir
    if args.json:
        run = run_demo(trace_dir=trace_dir)
        payload = {
            "result": run.result.to_dict(),
            "receipt": run.shop.order_payload(run.order) if run.order else None,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if run.result.status == "ok" else 1

    print("🍵 波波茶铺 · Boba Harness MVP")
    print(f"👤 顾客：{DEMO_USER_MESSAGE}\n")
    run = run_demo(trace_dir=trace_dir, on_event=EventPrinter())
    print()
    if run.result.status == "ok":
        print(
            f"✅ 完成 · {run.result.turns} 轮模型 · "
            f"{run.result.tool_calls} 次工具调用"
        )
    else:
        print(f"⚠️ 结束状态：{run.result.status}")
    if run.result.trace_path is not None:
        print(f"🧾 小票流水：{run.result.trace_path}")
    return 0 if run.result.status == "ok" else 1


def cmd_chat(args: argparse.Namespace) -> int:
    shop = Shop.load()
    agent = build_barista(shop)
    try:
        model = AnthropicModel(
            model=args.model,
            effort=args.effort,
            fallbacks=not args.no_fallbacks,
        )
    except RuntimeError as exc:
        print(f"❌ {exc}")
        print("   然后设置 ANTHROPIC_API_KEY，或先运行 `python -m boba demo`（无需 key）。")
        return 2

    harness = Harness(
        agent=agent,
        model=model,
        config=HarnessConfig(
            max_turns=args.max_turns,
            trace=not args.no_trace,
            trace_dir=args.trace_dir,
        ),
        resources={"shop": shop},
        guardrails=[MaxCupsPerOrder(10)],
        on_event=EventPrinter(),
    )

    print("🍵 波波茶铺已营业。输入 /quit 打烊，/menu 看菜单。")
    session = Session()
    while True:
        try:
            line = input("👤 顾客：")
        except (EOFError, KeyboardInterrupt):
            print("\n👋 打烊啦。")
            break
        line = line.strip()
        if not line:
            continue
        if line in {"/quit", "/exit", "/bye"}:
            print("👋 打烊啦。")
            break
        if line == "/menu":
            _print_menu(shop)
            continue
        try:
            result = harness.run(line, session=session)
        except KeyboardInterrupt:
            print("\n⏹️ 已中断本轮。")
            continue
        if result.status != "ok":
            print(f"   ⚠️ 本轮结束状态：{result.status}")
        if args.verbose and result.trace_path is not None:
            print(f"   🧾 {result.trace_path}")
    if not args.no_trace:
        print(f"🧾 小票都在：{Path(args.trace_dir)}")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    events = load_events(args.path)
    if args.json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return 0
    print(f"🧾 {args.path}")
    print(render_events(events, verbose=args.verbose))
    return 0


def cmd_menu(args: argparse.Namespace) -> int:
    shop = Shop.load()
    if args.json:
        print(json.dumps(shop.menu_payload(), ensure_ascii=False, indent=2))
    else:
        _print_menu(shop)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boba",
        description="波波茶铺：用一间奶茶店讲清楚 Agent Harness。",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command")

    demo = subparsers.add_parser("demo", help="跑一遍离线点单演示（无需 API key）")
    demo.add_argument("--trace-dir", default="traces", help="小票目录，默认 traces/")
    demo.add_argument("--no-trace", action="store_true", help="不写小票文件")
    demo.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    demo.set_defaults(func=cmd_demo)

    chat = subparsers.add_parser("chat", help="接入真实 Claude 模型接待顾客")
    chat.add_argument("--model", default=DEFAULT_MODEL, help=f"默认 {DEFAULT_MODEL}")
    chat.add_argument(
        "--effort",
        default="medium",
        choices=sorted(EFFORT_LEVELS),
        help="思考/花费档位，默认 medium",
    )
    chat.add_argument("--max-turns", type=int, default=8, help="单轮最多模型回合数")
    chat.add_argument("--trace-dir", default="traces", help="小票目录")
    chat.add_argument("--no-trace", action="store_true", help="不写小票文件")
    chat.add_argument(
        "--no-fallbacks",
        action="store_true",
        help="关闭服务端 refusal fallback",
    )
    chat.add_argument("--verbose", action="store_true", help="显示每次运行的小票路径")
    chat.set_defaults(func=cmd_chat)

    trace = subparsers.add_parser("trace", help="把小票 JSONL 渲染成时间线")
    trace.add_argument("path", help="小票文件路径")
    trace.add_argument("--json", action="store_true", help="原样输出 JSON 事件")
    trace.add_argument("--verbose", action="store_true", help="包含模型请求等细节")
    trace.set_defaults(func=cmd_trace)

    menu = subparsers.add_parser("menu", help="打印今日菜单")
    menu.add_argument("--json", action="store_true", help="输出 JSON")
    menu.set_defaults(func=cmd_menu)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
