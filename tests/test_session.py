import unittest

from boba.guardrails import GuardrailRegistry, MaxCupsPerOrder
from boba.session import (
    MaxCupsPerSession,
    SessionState,
    SessionStore,
    place_order,
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


class SessionStateTest(unittest.TestCase):
    def test_total_cups_aggregates_orders(self) -> None:
        session = SessionState("table-3")
        session.add_order("B1001", 3)
        session.add_order("B1002", 7)

        self.assertEqual(session.total_cups, 10)

    def test_find_order_only_sees_own_orders(self) -> None:
        session = SessionState("table-3")
        session.add_order("B1001", 3)

        self.assertEqual(session.find_order("B1001")["quantity"], 3)
        self.assertIsNone(session.find_order("B9999"))


class SessionStoreTest(unittest.TestCase):
    def test_sessions_are_isolated(self) -> None:
        store = SessionStore()
        table_3 = store.get("table-3")
        table_5 = store.get("table-5")
        table_3.add_order("B1001", 5)

        self.assertEqual(table_3.total_cups, 5)
        self.assertEqual(table_5.total_cups, 0)
        self.assertIsNone(table_5.find_order("B1001"))

    def test_same_id_returns_same_notebook(self) -> None:
        store = SessionStore()
        store.get("table-3").add_order("B1001", 4)

        self.assertEqual(store.get("table-3").total_cups, 4)


class MaxCupsPerSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guardrail = MaxCupsPerSession(10)
        self.session = SessionState("table-3")

    def test_allows_up_to_session_limit(self) -> None:
        self.session.add_order("B1001", 5)

        self.assertTrue(self.guardrail.check(order_call(5), self.session).allowed)

    def test_denies_over_session_limit(self) -> None:
        self.session.add_order("B1001", 5)

        decision = self.guardrail.check(order_call(6), self.session)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_denied")
        self.assertIn("5", decision.message)
        self.assertIn("6", decision.message)

    def test_split_order_denied_on_second_slip(self) -> None:
        self.assertTrue(self.guardrail.check(order_call(10), self.session).allowed)
        self.session.add_order("B1001", 10)

        decision = self.guardrail.check(order_call(10, "call_2"), self.session)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "permission_denied")
        self.assertEqual(self.session.total_cups, 10)

    def test_missing_session_fails_closed(self) -> None:
        decision = self.guardrail.check(order_call(1), None)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "guardrail_error")

    def test_ignores_other_tools(self) -> None:
        decision = self.guardrail.check(
            ToolCall("call_2", "inventory_check", {"item": "boba_milk_tea"}),
            self.session,
        )
        self.assertTrue(decision.allowed)


class PlaceOrderTest(unittest.TestCase):
    def test_successful_order_is_added_to_session(self) -> None:
        session = SessionState("table-3")
        result = place_order(
            session,
            order_call(5),
            build_registry(),
            GuardrailRegistry([MaxCupsPerSession(10)]),
        )

        self.assertFalse(result.is_error)
        self.assertEqual(session.total_cups, 5)

    def test_denied_order_is_not_added_to_session(self) -> None:
        session = SessionState("table-3")
        session.add_order("B1001", 10)
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
        result = place_order(
            session,
            order_call(10, "call_2"),
            tools,
            GuardrailRegistry([MaxCupsPerSession(10)]),
        )

        self.assertTrue(result.is_error)
        self.assertEqual(result.content["error"]["code"], "permission_denied")
        self.assertEqual(called, [])
        self.assertEqual(session.total_cups, 10)

    def test_both_order_and_session_guardrails_apply(self) -> None:
        session = SessionState("table-3")
        guardrails = GuardrailRegistry([MaxCupsPerOrder(10), MaxCupsPerSession(10)])

        result = place_order(session, order_call(20), build_registry(), guardrails)

        self.assertTrue(result.is_error)
        self.assertEqual(result.content["error"]["code"], "permission_denied")
        self.assertEqual(session.total_cups, 0)


if __name__ == "__main__":
    unittest.main()
