"""Lesson 06 · 监控录像：trace 与 eval。

一次运行就是一串事件：开始、模型说话、调工具、被护栏拒绝、
写状态、结束。trace 只追加，不改写；出了问题能按 seq 回放。
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class TraceEvent:
    seq: int
    ts: float
    run_id: str
    type: str
    data: dict[str, Any]


class Trace:
    """一次运行的事件流。append-only，一条事件一行。"""

    def __init__(self, run_id: str, clock: Callable[[], float] = time.time) -> None:
        self.run_id = run_id
        self._clock = clock
        self.events: list[TraceEvent] = []

    def emit(self, event_type: str, **data: Any) -> TraceEvent:
        event = TraceEvent(
            seq=len(self.events) + 1,
            ts=self._clock(),
            run_id=self.run_id,
            type=event_type,
            data=data,
        )
        self.events.append(event)
        return event

    def to_jsonl(self) -> str:
        return "\n".join(
            json.dumps(asdict(event), ensure_ascii=False) for event in self.events
        )

    def write(self, path: str | Path) -> None:
        text = self.to_jsonl()
        Path(path).write_text(text + ("\n" if text else ""), encoding="utf-8")

    @classmethod
    def from_jsonl(cls, text: str) -> "Trace":
        events = [
            TraceEvent(**json.loads(line))
            for line in text.splitlines()
            if line.strip()
        ]
        trace = cls(events[0].run_id if events else "")
        trace.events = events
        return trace

    @classmethod
    def read(cls, path: str | Path) -> "Trace":
        return cls.from_jsonl(Path(path).read_text(encoding="utf-8"))

    def status(self) -> str:
        """以最后一条 run.end 为准；没有 run.end 就是没正常收尾。"""
        for event in reversed(self.events):
            if event.type == "run.end":
                return event.data.get("status") or "error"
        return "incomplete"

    def summary(self) -> dict[str, Any]:
        counts = Counter(event.type for event in self.events)
        elapsed = (
            self.events[-1].ts - self.events[0].ts if self.events else 0.0
        )
        return {
            "run_id": self.run_id,
            "status": self.status(),
            "events": len(self.events),
            "model_turns": counts["model.turn"],
            "tool_calls": counts["tool.call"],
            "denials": counts["guardrail.denied"],
            "errors": sum(
                1
                for event in self.events
                if event.type == "tool.result" and event.data.get("is_error")
            ),
            "elapsed": round(elapsed, 3),
        }


def demo() -> None:
    trace = Trace("run_20261119_001")
    trace.emit("run.start", user="3 号桌要 20 杯")
    trace.emit("model.turn", text="拆成两单，每单 10 杯")
    trace.emit("tool.call", call_id="call_1", tool="order_create", quantity=10)
    trace.emit("tool.result", call_id="call_1", is_error=False)
    trace.emit("state.write", total_cups=10)
    trace.emit("model.turn", text="再下一单")
    trace.emit("tool.call", call_id="call_2", tool="order_create", quantity=10)
    trace.emit("guardrail.denied", call_id="call_2", code="permission_denied")
    trace.emit("tool.result", call_id="call_2", is_error=True)
    trace.emit("run.end", status="permission_denied")

    print(trace.to_jsonl())
    print(trace.summary())


if __name__ == "__main__":
    demo()
