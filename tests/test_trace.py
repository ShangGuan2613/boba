from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from boba.trace import Trace, load_events, render_events


class TraceTest(unittest.TestCase):
    def test_writes_jsonl_and_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace = Trace("run_test", tmp)
            trace.emit("run.started", {"agent": "小波", "model": "scripted", "tools": []})
            trace.emit("session.message", {"role": "user", "text": "你好"})
            trace.emit(
                "tool.result",
                {"tool": "menu_list", "ok": True, "duration_ms": 1.0, "result": {}},
            )
            trace.emit("run.finished", {"status": "ok", "turns": 1, "tool_calls": 0})
            path = trace.path
            trace.close()

            self.assertIsNotNone(path)
            events = load_events(path)
            self.assertEqual([event["seq"] for event in events], [1, 2, 3, 4])
            self.assertTrue(all(event["run_id"] == "run_test" for event in events))

            rendered = render_events(events)
            self.assertIn("run.started", rendered)
            self.assertIn("🧾", rendered)
            self.assertIn("你好", rendered)

    def test_model_request_hidden_unless_verbose(self) -> None:
        events = [
            {"seq": 1, "type": "model.request", "data": {"turn": 1, "message_count": 1}},
            {"seq": 2, "type": "run.finished", "data": {"status": "ok"}},
        ]
        self.assertNotIn("model.request", render_events(events))
        self.assertIn("model.request", render_events(events, verbose=True))

    def test_in_memory_trace_has_no_file(self) -> None:
        trace = Trace("run_memory", None)
        trace.emit("run.started", {})
        trace.close()
        self.assertIsNone(trace.path)
        self.assertEqual(len(trace.events), 1)

    def test_bad_json_line_reports_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text(json.dumps({"seq": 1}) + "\nnot-json\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bad.jsonl:2"):
                load_events(path)


if __name__ == "__main__":
    unittest.main()
