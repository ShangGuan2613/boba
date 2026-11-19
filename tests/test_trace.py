import tempfile
import unittest
from pathlib import Path

from boba.trace import Trace, TraceEvent


def fixed_clock(*times):
    values = iter(times)
    return lambda: next(values)


class TraceTest(unittest.TestCase):
    def test_emit_assigns_seq_and_run_id(self) -> None:
        trace = Trace("run_1", clock=fixed_clock(1.0, 2.0))
        first = trace.emit("run.start")
        second = trace.emit("model.turn")

        self.assertEqual(first.seq, 1)
        self.assertEqual(second.seq, 2)
        self.assertEqual(first.run_id, "run_1")
        self.assertEqual(first.ts, 1.0)
        self.assertEqual(second.ts, 2.0)

    def test_jsonl_round_trip(self) -> None:
        trace = Trace("run_1", clock=fixed_clock(1.0, 2.0))
        trace.emit("run.start", user="3 号桌")
        trace.emit("run.end", status="ok")

        restored = Trace.from_jsonl(trace.to_jsonl())

        self.assertEqual(restored.run_id, "run_1")
        self.assertEqual(restored.events, trace.events)
        self.assertEqual(restored.status(), "ok")

    def test_status_reads_last_run_end(self) -> None:
        trace = Trace("run_1")
        trace.emit("run.start")
        trace.emit("run.end", status="permission_denied")

        self.assertEqual(trace.status(), "permission_denied")

    def test_status_is_incomplete_without_run_end(self) -> None:
        trace = Trace("run_1")
        trace.emit("run.start")
        trace.emit("tool.call", tool="order_create")

        self.assertEqual(trace.status(), "incomplete")

    def test_summary_counts_events(self) -> None:
        trace = Trace("run_1", clock=fixed_clock(1.0, 1.1, 1.2, 1.3, 1.4, 1.5))
        trace.emit("run.start")
        trace.emit("model.turn")
        trace.emit("tool.call", tool="order_create")
        trace.emit("guardrail.denied", code="permission_denied")
        trace.emit("tool.result", is_error=True)
        trace.emit("run.end", status="permission_denied")

        self.assertEqual(
            trace.summary(),
            {
                "run_id": "run_1",
                "status": "permission_denied",
                "events": 6,
                "model_turns": 1,
                "tool_calls": 1,
                "denials": 1,
                "errors": 1,
                "elapsed": 0.5,
            },
        )

    def test_write_and_read_file(self) -> None:
        trace = Trace("run_1", clock=fixed_clock(1.0))
        trace.emit("run.start")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            trace.write(path)
            restored = Trace.read(path)
            text = path.read_text(encoding="utf-8")

        self.assertEqual(restored.events, trace.events)
        self.assertEqual(text.count("\n"), 1)

    def test_empty_trace_is_incomplete(self) -> None:
        self.assertEqual(Trace("run_1").status(), "incomplete")


class TraceEventTest(unittest.TestCase):
    def test_event_is_frozen(self) -> None:
        event = TraceEvent(1, 1.0, "run_1", "run.start", {})

        with self.assertRaises(Exception):
            event.seq = 2


if __name__ == "__main__":
    unittest.main()
