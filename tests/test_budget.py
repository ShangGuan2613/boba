import unittest

from boba.budget import Budget, BudgetExceeded, budget_error_result
from boba.tool_protocol import ToolCall


class BudgetTest(unittest.TestCase):
    def make_budget(self, **kwargs):
        now = [100.0]
        budget = Budget(clock=lambda: now[0], **kwargs)
        return budget, now

    def test_turn_limit_stops_before_extra_turn(self) -> None:
        budget, _ = self.make_budget(max_turns=2)

        budget.start_turn()
        budget.start_turn()

        with self.assertRaises(BudgetExceeded) as caught:
            budget.start_turn()

        self.assertEqual(caught.exception.status, "max_turns")
        self.assertEqual(budget.turns, 2)

    def test_tool_call_limit_stops_before_extra_tool(self) -> None:
        budget, _ = self.make_budget(max_tool_calls=2)

        budget.start_tool()
        budget.start_tool()

        with self.assertRaises(BudgetExceeded) as caught:
            budget.start_tool()

        self.assertEqual(caught.exception.status, "max_tool_calls")
        self.assertEqual(budget.tool_calls, 2)

    def test_timeout_uses_injected_clock(self) -> None:
        budget, now = self.make_budget(max_seconds=10)

        budget.start_turn()
        now[0] += 11

        with self.assertRaises(BudgetExceeded) as caught:
            budget.start_turn()

        self.assertEqual(caught.exception.status, "timeout")

    def test_timeout_takes_precedence_over_turn_limit(self) -> None:
        budget, now = self.make_budget(max_turns=1, max_seconds=10)

        budget.start_turn()
        now[0] += 11

        with self.assertRaises(BudgetExceeded) as caught:
            budget.start_turn()

        self.assertEqual(caught.exception.status, "timeout")

    def test_last_turn_can_still_call_tools(self) -> None:
        budget, _ = self.make_budget(max_turns=1, max_tool_calls=2)

        budget.start_turn()
        budget.start_tool()
        budget.start_tool()

        self.assertEqual(budget.turns, 1)
        self.assertEqual(budget.tool_calls, 2)

    def test_tool_budget_does_not_block_final_text_turn(self) -> None:
        budget, _ = self.make_budget(max_turns=2, max_tool_calls=1)

        budget.start_turn()
        budget.start_tool()
        budget.start_turn()

        self.assertEqual(budget.turns, 2)
        self.assertEqual(budget.tool_calls, 1)

    def test_snapshot_reports_current_usage(self) -> None:
        budget, _ = self.make_budget()

        budget.start_turn()
        budget.start_tool()

        self.assertEqual(
            budget.snapshot(),
            {"turns": 1, "tool_calls": 1, "elapsed": 0.0},
        )

    def test_budget_error_result_closes_pending_call(self) -> None:
        call = ToolCall("call_17", "inventory_check", {"item": "boba_milk_tea"})

        result = budget_error_result(call, "max_tool_calls")

        self.assertEqual(result.tool_use_id, "call_17")
        self.assertTrue(result.is_error)
        self.assertEqual(result.content["error"]["code"], "budget_exhausted")
        self.assertIn("max_tool_calls", result.content["error"]["message"])


if __name__ == "__main__":
    unittest.main()
