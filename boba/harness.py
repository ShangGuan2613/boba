"""门店运营体系（Harness）。

Harness 负责：
- 把顾客消息放进会话；
- 驱动「模型 -> 工具 -> 模型」循环；
- 派发工具、执行店长守则、记录小票；
- 用轮数/工具数/时间预算收口。

它不认识奶茶，只认识 Agent / Model / Tool / Guardrail。
"""

from __future__ import annotations

import copy
import json
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .core import (
    Agent,
    Guardrail,
    Model,
    Tool,
    ToolCall,
    ToolContext,
    ToolError,
    tool_result_block,
)
from .trace import Trace

__all__ = [
    "Harness",
    "HarnessConfig",
    "RunResult",
    "Session",
    "assistant_message",
    "tool_results_message",
    "user_message",
]


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def assistant_message(content: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "assistant", "content": list(content)}


def tool_results_message(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "user", "content": list(results)}


@dataclass
class HarnessConfig:
    """门店预算与流水设置。"""

    max_turns: int = 8
    max_tool_calls: int = 16
    max_seconds: float = 60.0
    trace: bool = True
    trace_dir: Path | None = Path("traces")

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            raise ValueError("max_turns 必须 >= 1")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls 必须 >= 0")
        if self.max_seconds <= 0:
            raise ValueError("max_seconds 必须 > 0")
        if self.trace and self.trace_dir is not None:
            self.trace_dir = Path(self.trace_dir)


@dataclass
class Session:
    """一次接待：同一 session 的多轮消息共享上下文。"""

    id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")
    messages: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunResult:
    run_id: str
    session_id: str
    status: str
    text: str
    turns: int
    tool_calls: int
    messages: list[dict[str, Any]]
    events: list[dict[str, Any]]
    trace_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "status": self.status,
            "text": self.text,
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "trace_path": str(self.trace_path) if self.trace_path else None,
        }


class Harness:
    def __init__(
        self,
        *,
        agent: Agent,
        model: Model,
        config: HarnessConfig | None = None,
        resources: Mapping[str, Any] | None = None,
        guardrails: Sequence[Guardrail] = (),
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.agent = agent
        self.model = model
        self.config = config or HarnessConfig()
        self.resources = dict(resources or {})
        self.guardrails = list(guardrails)
        self.on_event = on_event
        self._tools: dict[str, Tool] = {tool.name: tool for tool in agent.tools}

    def run(self, user_text: str, *, session: Session | None = None) -> RunResult:
        if not isinstance(user_text, str):
            raise TypeError("user_text 必须是字符串")

        session = session or Session()
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        trace = Trace(run_id, self.config.trace_dir if self.config.trace else None)
        started = time.monotonic()

        def emit(event_type: str, data: dict[str, Any] | None = None) -> None:
            event = trace.emit(event_type, data or {})
            if self.on_event is None:
                return
            try:
                self.on_event(event)
            except Exception as exc:  # UI 不能把门店搞停业
                trace.emit(
                    "ui.error",
                    {"error": f"{type(exc).__name__}: {exc}"},
                )

        status = "ok"
        final_text = ""
        turns = 0
        tool_call_count = 0

        emit(
            "run.started",
            {
                "agent": self.agent.name,
                "model": getattr(self.model, "label", None)
                or getattr(self.model, "name", type(self.model).__name__),
                "session_id": session.id,
                "tools": [tool.name for tool in self.agent.tools],
                "limits": {
                    "max_turns": self.config.max_turns,
                    "max_tool_calls": self.config.max_tool_calls,
                    "max_seconds": self.config.max_seconds,
                },
            },
        )
        emit("session.message", {"role": "user", "text": user_text})
        session.messages.append(user_message(user_text))

        ctx = ToolContext(
            run_id=run_id,
            session_id=session.id,
            resources=self.resources,
            emit=emit,
        )

        try:
            while True:
                if turns >= self.config.max_turns:
                    status = "max_turns"
                    emit(
                        "harness.stopped",
                        {"reason": "max_turns", "limit": self.config.max_turns},
                    )
                    break

                elapsed = time.monotonic() - started
                if elapsed > self.config.max_seconds:
                    status = "timeout"
                    emit(
                        "harness.stopped",
                        {
                            "reason": "timeout",
                            "elapsed_ms": round(elapsed * 1000, 2),
                            "limit_seconds": self.config.max_seconds,
                        },
                    )
                    break

                turns += 1
                emit(
                    "model.request",
                    {
                        "turn": turns,
                        "message_count": len(session.messages),
                        "tools": [tool.name for tool in self.agent.tools],
                    },
                )

                try:
                    model_turn = self.model.generate(
                        system=self.agent.system_prompt,
                        messages=session.messages,
                        tools=self.agent.tools,
                    )
                except Exception as exc:
                    status = "model_error"
                    emit(
                        "model.error",
                        {
                            "turn": turns,
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(),
                        },
                    )
                    break

                emit(
                    "model.response",
                    {
                        "turn": turns,
                        "stop_reason": model_turn.stop_reason,
                        "text": model_turn.text,
                        "tool_calls": [
                            {"id": item.id, "name": item.name, "arguments": item.arguments}
                            for item in model_turn.tool_calls
                        ],
                    },
                )

                if model_turn.content:
                    session.messages.append(assistant_message(model_turn.content))
                if model_turn.text:
                    final_text = model_turn.text

                if model_turn.stop_reason == "refusal":
                    status = "refusal"
                    emit("harness.stopped", {"reason": "model_refusal"})
                    break

                calls = model_turn.tool_calls
                if not calls:
                    break

                results: list[dict[str, Any]] = []
                budget_hit: str | None = None
                for tool_call in calls:
                    if budget_hit is None:
                        if tool_call_count >= self.config.max_tool_calls:
                            budget_hit = "max_tool_calls"
                        elif time.monotonic() - started > self.config.max_seconds:
                            budget_hit = "timeout"

                    if budget_hit is not None:
                        results.append(
                            tool_result_block(
                                tool_call.id,
                                _dump({"error": f"harness: {budget_hit} 预算已用尽"}),
                                is_error=True,
                            )
                        )
                        emit(
                            "tool.skipped",
                            {
                                "id": tool_call.id,
                                "tool": tool_call.name,
                                "reason": budget_hit,
                            },
                        )
                        continue

                    tool_call_count += 1
                    results.append(self._call_tool(tool_call, ctx, emit))

                session.messages.append(tool_results_message(results))

                if budget_hit is not None:
                    status = budget_hit
                    emit(
                        "harness.stopped",
                        {"reason": budget_hit, "limit": self.config.max_tool_calls},
                    )
                    break

        except Exception as exc:  # 门店兜底：流水必须留下
            status = "harness_error"
            final_text = final_text or "门店运营出了点问题，请查看小票流水。"
            emit(
                "harness.error",
                {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()},
            )
        finally:
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            emit(
                "run.finished",
                {
                    "status": status,
                    "turns": turns,
                    "tool_calls": tool_call_count,
                    "duration_ms": duration_ms,
                },
            )
            trace.close()

        return RunResult(
            run_id=run_id,
            session_id=session.id,
            status=status,
            text=final_text,
            turns=turns,
            tool_calls=tool_call_count,
            messages=copy.deepcopy(session.messages),
            events=list(trace.events),
            trace_path=trace.path,
        )

    def _call_tool(
        self,
        call: ToolCall,
        ctx: ToolContext,
        emit: Callable[[str, dict[str, Any] | None], None],
    ) -> dict[str, Any]:
        emit(
            "tool.call",
            {"id": call.id, "tool": call.name, "arguments": call.arguments},
        )

        tool = self._tools.get(call.name)
        if tool is None:
            message = (
                f"未知工具 {call.name!r}；可用工具：{', '.join(sorted(self._tools))}"
            )
            emit(
                "tool.result",
                {
                    "id": call.id,
                    "tool": call.name,
                    "ok": False,
                    "duration_ms": 0,
                    "error": message,
                },
            )
            return tool_result_block(call.id, _dump({"error": message}), is_error=True)

        if not isinstance(call.arguments, dict):
            message = "工具参数必须是 JSON object"
            emit(
                "tool.result",
                {
                    "id": call.id,
                    "tool": call.name,
                    "ok": False,
                    "duration_ms": 0,
                    "error": message,
                },
            )
            return tool_result_block(call.id, _dump({"error": message}), is_error=True)

        for guardrail in self.guardrails:
            try:
                reason = guardrail.check(tool=tool, arguments=call.arguments, ctx=ctx)
            except Exception as exc:
                reason = (
                    f"护栏 {type(guardrail).__name__} 异常，已保守拒绝：{exc}"
                )
                emit(
                    "guardrail.error",
                    {
                        "tool": call.name,
                        "guardrail": type(guardrail).__name__,
                        "error": str(exc),
                    },
                )
            if reason:
                emit(
                    "guardrail.denied",
                    {
                        "tool": call.name,
                        "arguments": call.arguments,
                        "reason": reason,
                    },
                )
                return tool_result_block(
                    call.id, _dump({"error": reason}), is_error=True
                )

        tool_started = time.monotonic()
        try:
            result = tool.handler(ctx, call.arguments)
            ok = True
            error = None
        except ToolError as exc:
            ok = False
            error = str(exc)
            result = None
        except Exception as exc:
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            result = None
            emit(
                "tool.error",
                {
                    "tool": call.name,
                    "error": error,
                    "traceback": traceback.format_exc(),
                },
            )
        duration_ms = round((time.monotonic() - tool_started) * 1000, 2)

        if ok:
            emit(
                "tool.result",
                {
                    "id": call.id,
                    "tool": call.name,
                    "ok": True,
                    "duration_ms": duration_ms,
                    "result": result,
                },
            )
            content = _dump(result)
        else:
            emit(
                "tool.result",
                {
                    "id": call.id,
                    "tool": call.name,
                    "ok": False,
                    "duration_ms": duration_ms,
                    "error": error,
                },
            )
            content = _dump({"error": error})

        return tool_result_block(call.id, content, is_error=not ok)
