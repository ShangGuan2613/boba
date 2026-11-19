import unittest

from boba.guardrails import (
    GuardrailDecision,
    GuardrailRegistry,
    MaxCupsPerOrder,
    denied_result,
    run_guarded,
)
from boba.tool_protocol import Tool, ToolCall, ToolRegistry, build_registry


def order_call(quantity: int, call_id: str = "call_1") -> ToolCall:
    return ToolCall(
        call_id,
        "order_create",
        {
            "item": "boba_milk_tea",
            "size": "中杯",
            "ice": "少冰",
            "sugar": "三分糖",
            "quantity": quantity,
        },
    )


class MaxCupsPerOrderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guardrail = MaxCupsPerOrder(10)

    def test_allows_up_to_limit(self) -> None:
        self.assertTrue(self.guardrail.check(order_call(10)).allowed)

    def test_denies_over_limit(self) -> None:
        decision = self.guardrail.check(order_call(11))

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_denied")
        self.assertIn("10", decision.message)
        self.assertIn("11", decision.message)

    def test_ignores_other_tools(self) -> None:
        decision = self.guardrail.check(
            ToolCall("call_2", "inventory_check", {"item": "boba_milk_tea"})
        )
        self.assertTrue(decision.allowed)

    def test_denies_invalid_quantity(self) -> None:
        decision = self.guardrail.check(
            ToolCall(
                "call_3",
                "order_create",
                {"item": "boba_milk_tea", "size": "中杯", "ice": "少冰", "sugar": "三分糖", "quantity": 0},
            )
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "invalid_quantity")


class GuardrailRegistryTest(unittest.TestCase):
    def test_first_denial_wins(self) -> None:
        registry = GuardrailRegistry([MaxCupsPerOrder(10)])
        decision = registry.check(order_call(20))

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_denied")

    def test_fails_closed_when_guardrail_raises(self) -> None:
        class Broken:
            name = "broken"

            def check(self, call, session=None):
                raise RuntimeError("规则数据加载失败")

        decision = GuardrailRegistry([Broken()]).check(order_call(1))

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "guardrail_error")

    def test_denied_result_keeps_call_id(self) -> None:
        decision = GuardrailDecision(False, "permission_denied", "最多 10 杯", "转人工")
        result = denied_result(order_call(20, "call_9"), decision)

        self.assertEqual(result.tool_use_id, "call_9")
        self.assertTrue(result.is_error)
        self.assertEqual(result.content["error"]["code"], "permission_denied")


class RunGuardedTest(unittest.TestCase):
    def test_denied_call_never_executes_tool(self) -> None:
        called = []

        def spy(**args):
            called.append(args)
            return {"ok": True}

        tools = ToolRegistry(
            [
                Tool(
                    name="order_create",
                    description="spy",
                    required=(),
                    properties=("item", "size", "ice", "sugar", "quantity"),
                    fn=spy,
                )
            ]
        )
        guardrails = GuardrailRegistry([MaxCupsPerOrder(10)])

        result = run_guarded(order_call(20), tools, guardrails)

        self.assertTrue(result.is_error)
        self.assertEqual(result.content["error"]["code"], "permission_denied")
        self.assertEqual(called, [])

    def test_allowed_call_executes_tool(self) -> None:
        result = run_guarded(
            order_call(10),
            build_registry(),
            GuardrailRegistry([MaxCupsPerOrder(10)]),
        )

        self.assertFalse(result.is_error)
        self.assertEqual(result.content["data"]["quantity"], 10)
        self.assertEqual(result.content["data"]["total"], 120)


if __name__ == "__main__":
    unittest.main()
