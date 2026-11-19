from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout

from boba.barista import build_barista
from boba.cli import main
from boba.core import call, say
from boba.demo import run_demo
from boba.harness import Harness, HarnessConfig
from boba.models import ScriptedModel
from boba.shop import MaxCupsPerOrder, Shop
from boba.trace import load_events


class DemoTests(unittest.TestCase):
    def test_demo_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = run_demo(trace_dir=tmp)

            self.assertEqual(run.result.status, "ok")
            self.assertIsNotNone(run.order)
            self.assertEqual(run.order.id, "B1001")
            self.assertEqual(run.order.status, "submitted")
            self.assertEqual(run.order.total_cents, 2400)
            self.assertIn("B1001", run.result.text)
            self.assertIn("¥24", run.result.text)
            self.assertIn("6 分钟", run.result.text)

            self.assertAlmostEqual(run.shop.inventory["black_tea_ml"], 3600)
            self.assertAlmostEqual(run.shop.inventory["milk_ml"], 2300)
            self.assertAlmostEqual(run.shop.inventory["tapioca_g"], 700)

            self.assertIsNotNone(run.result.trace_path)
            events = load_events(run.result.trace_path)
            types = [event["type"] for event in events]
            self.assertIn("run.finished", types)
            tools = [
                event["data"]["tool"]
                for event in events
                if event["type"] == "tool.call"
            ]
            self.assertEqual(
                tools,
                [
                    "menu_list",
                    "inventory_check",
                    "order_create",
                    "order_add_item",
                    "order_add_item",
                    "order_submit",
                ],
            )

    def test_demo_without_trace(self) -> None:
        run = run_demo(trace_dir=None)
        self.assertEqual(run.result.status, "ok")
        self.assertIsNone(run.result.trace_path)
        self.assertEqual([event["type"] for event in run.result.events][-1], "run.finished")

    def test_cup_guardrail_blocks_oversized_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shop = Shop.load()
            model = ScriptedModel(
                [
                    call("order_add_item", item_id="boba_milk_tea", qty=11),
                    say("店长说单笔最多十杯哦。"),
                ]
            )
            harness = Harness(
                agent=build_barista(shop),
                model=model,
                config=HarnessConfig(trace_dir=tmp),
                resources={"shop": shop},
                guardrails=[MaxCupsPerOrder(10)],
            )
            result = harness.run("来十一杯")

            self.assertEqual(result.status, "ok")
            self.assertIsNone(shop.last_order())
            denied = [
                event for event in result.events if event["type"] == "guardrail.denied"
            ]
            self.assertEqual(len(denied), 1)
            self.assertIn("最多 10 杯", denied[0]["data"]["reason"])

    def test_cli_demo_json(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["demo", "--no-trace", "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["result"]["status"], "ok")
        self.assertEqual(payload["receipt"]["order_id"], "B1001")
        self.assertEqual(payload["receipt"]["total"], 24)


if __name__ == "__main__":
    unittest.main()
