"""小票流水（trace）。

一次 run 对应一张小票：每一轮模型调用、每一次工具调用、每一次护栏拦截
都按顺序落成 JSONL。它既是调试工具，也是后续评测（试饮会）的原料。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .util import clip, utc_now_iso

__all__ = ["Trace", "TraceEvent", "load_events", "render_events"]


@dataclass
class TraceEvent:
    seq: int
    ts: str
    run_id: str
    type: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "run_id": self.run_id,
            "type": self.type,
            "data": self.data,
        }


class Trace:
    """按 run 追加写入 JSONL；没有目录时只留在内存。"""

    def __init__(self, run_id: str, directory: str | Path | None = None) -> None:
        self.run_id = run_id
        self.events: list[dict[str, Any]] = []
        self.path: Path | None = None
        self._seq = 0
        self._lock = threading.Lock()
        self._fh = None

        if directory is not None:
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            self.path = directory / f"{stamp}-{run_id}.jsonl"
            self._fh = self.path.open("a", encoding="utf-8")

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            event = TraceEvent(
                seq=self._seq,
                ts=utc_now_iso(),
                run_id=self.run_id,
                type=event_type,
                data=data or {},
            ).to_dict()
            self.events.append(event)
            if self._fh is not None:
                self._fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
                self._fh.flush()
            return event

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None


_SYMBOLS = {
    "run.started": "🏁",
    "session.message": "👤",
    "model.response": "🧑‍🍳",
    "tool.call": "🔧",
    "tool.result": "✅",
    "tool.skipped": "⏭️",
    "guardrail.denied": "🛑",
    "guardrail.error": "🛑",
    "harness.stopped": "⏹️",
    "run.finished": "🧾",
    "model.error": "❌",
    "tool.error": "❌",
    "harness.error": "❌",
    "ui.error": "❌",
}


def _detail(event: dict[str, Any]) -> str:
    event_type = event.get("type", "")
    data = event.get("data") or {}

    if event_type == "run.started":
        tools = data.get("tools") or []
        return f"{data.get('agent', '?')} · {data.get('model', '?')} · {len(tools)} 件工具"
    if event_type == "session.message":
        return clip(data.get("text", ""), 120)
    if event_type == "model.request":
        return f"第 {data.get('turn', '?')} 轮 · {data.get('message_count', '?')} 条消息"
    if event_type == "model.response":
        parts = [f"第 {data.get('turn', '?')} 轮", str(data.get("stop_reason", ""))]
        if data.get("text"):
            parts.append(clip(data["text"], 100))
        return " · ".join(part for part in parts if part)
    if event_type == "tool.call":
        args = json.dumps(data.get("arguments", {}), ensure_ascii=False)
        return clip(f"{data.get('tool', '?')}({args})", 120)
    if event_type == "tool.result":
        if data.get("ok"):
            payload = json.dumps(data.get("result"), ensure_ascii=False, default=str)
            return clip(
                f"{data.get('tool', '?')} · {data.get('duration_ms', 0)}ms · {payload}",
                120,
            )
        return clip(
            f"{data.get('tool', '?')} 失败 · {data.get('error', '')}", 120
        )
    if event_type == "tool.skipped":
        return f"{data.get('tool', '?')} · {data.get('reason', '')}"
    if event_type in {"guardrail.denied", "guardrail.error"}:
        return clip(data.get("reason") or data.get("error") or "", 120)
    if event_type == "harness.stopped":
        return str(data.get("reason", ""))
    if event_type == "run.finished":
        return (
            f"{data.get('status', '?')} · {data.get('turns', 0)} 轮 · "
            f"{data.get('tool_calls', 0)} 次工具 · {data.get('duration_ms', 0)}ms"
        )
    if event_type in {"model.error", "tool.error", "harness.error", "ui.error"}:
        return clip(data.get("error", ""), 120)
    return clip(json.dumps(data, ensure_ascii=False, default=str), 120)


def render_events(events: Iterable[dict[str, Any]], *, verbose: bool = False) -> str:
    """把小票流水渲染成可读时间线。"""
    lines: list[str] = []
    for event in events:
        if event.get("type") == "model.request" and not verbose:
            continue
        symbol = _SYMBOLS.get(event.get("type", ""), "•")
        detail = _detail(event)
        lines.append(
            f"{event.get('seq', 0):>3} {symbol} {event.get('type', '?'):<16} {detail}"
        )
    return "\n".join(lines)


def load_events(path: str | Path) -> list[dict[str, Any]]:
    """读取 JSONL 小票流水。"""
    events: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} 不是合法 JSON: {exc}") from exc
    return events
