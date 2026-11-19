import unittest

from boba.eval import EvalCase, run_eval
from boba.trace import Trace


def trace_with_status(name: str, status: str) -> Trace:
    trace = Trace(name)
    trace.emit("run.start")
    trace.emit("run.end", status=status)
    return trace


class EvalTest(unittest.TestCase):
    def test_passing_cases(self) -> None:
        results = run_eval(
            [
                EvalCase("正常下单", "ok", trace_with_status("run_1", "ok")),
                EvalCase(
                    "超量被拦",
                    "permission_denied",
                    trace_with_status("run_2", "permission_denied"),
                ),
            ]
        )

        self.assertTrue(all(result.ok for result in results))
        self.assertEqual([result.name for result in results], ["正常下单", "超量被拦"])

    def test_mismatch_is_reported(self) -> None:
        results = run_eval(
            [EvalCase("应该超时", "timeout", trace_with_status("run_1", "ok"))]
        )

        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].expected, "timeout")
        self.assertEqual(results[0].actual, "ok")

    def test_empty_cases(self) -> None:
        self.assertEqual(run_eval([]), [])


if __name__ == "__main__":
    unittest.main()
