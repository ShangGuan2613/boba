import unittest

from boba.tool_protocol import ToolCall, build_registry


class ToolProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_registry()

    def test_missing_argument_returns_error_result(self) -> None:
        result = self.registry.run(
            ToolCall("call_1", "order_create", {"item": "boba_milk_tea"})
        )

        self.assertTrue(result.is_error)
        self.assertEqual(result.tool_use_id, "call_1")
        self.assertEqual(result.content["error"]["code"], "missing_argument")
        self.assertIn("size", result.content["error"]["message"])

    def test_unknown_tool_returns_error_result(self) -> None:
        result = self.registry.run(
            ToolCall("call_2", "get_discount", {"order_id": "B1001"})
        )

        self.assertTrue(result.is_error)
        self.assertEqual(result.content["error"]["code"], "unknown_tool")
        self.assertIn("get_discount", result.content["error"]["message"])

    def test_tool_exception_is_converted_not_raised(self) -> None:
        result = self.registry.run(
            ToolCall("call_3", "inventory_check", {"item": "boba_milk_tea"})
        )

        self.assertTrue(result.is_error)
        self.assertEqual(result.content["error"]["code"], "tool_failed")
        self.assertIn("RuntimeError", result.content["error"]["message"])

    def test_success_returns_data(self) -> None:
        result = self.registry.run(
            ToolCall(
                "call_4",
                "order_create",
                {"item": "boba_milk_tea", "size": "中杯", "ice": "少冰", "sugar": "三分糖"},
            )
        )

        self.assertFalse(result.is_error)
        self.assertEqual(result.content["ok"], True)
        self.assertEqual(result.content["data"]["order_id"], "B1001")
        self.assertEqual(result.content["data"]["total"], 12)

    def test_every_call_gets_exactly_one_result(self) -> None:
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

        results = [self.registry.run(call) for call in calls]

        self.assertEqual([r.tool_use_id for r in results], [c.id for c in calls])
        self.assertEqual(len(results), len(calls))


if __name__ == "__main__":
    unittest.main()
