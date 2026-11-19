from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from boba.core import (
    Agent,
    Tool,
    ToolError,
    call,
    say,
    tool_use_block,
    turn,
)
from boba.harness import Harness, HarnessConfig, Session
from boba.models import ScriptedModel
from boba.trace import load_events, render_events


def echo_tool() -> Tool:
    def handler(ctx, arguments):
        return {"echo": arguments.get("text", "")}

    return Tool(
        name="echo",
        description="原样返回 text",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=handler,
    )


def failing_tool() -> Tool:
    def handler(ctx, arguments):
        raise ToolError("缺珍珠了")

    return Tool(
        name="fail",
        description="总是失败",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=handler,
    )


def crashing_tool() -> Tool:
    def handler(ctx, arguments):
        raise RuntimeError("设备冒烟了")

    return Tool(
        name="crash",
        description="抛未预期异常",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=handler,
    )


def make_agent(*tools: Tool) -> Agent:
    return Agent(name="测试店员", system_prompt="你是测试店员。", tools=list(tools))


def tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        for block in message.get("content", []):
            if block.get("type") == "tool_result":
                results.append(block)
    return results


class HarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.trace_dir = Path(self.tmp.name) / "traces"

    def config(self, **overrides: Any) -> HarnessConfig:
        values = {"trace_dir": self.trace_dir, "max_turns": 8, "max_tool_calls": 16}
        values.update(overrides)
        return HarnessConfig(**values)

    def test_tool_then_answer(self) -> None:
        model = ScriptedModel([call("echo", text="你好"), say("收到")])
        harness = Harness(
            agent=make_agent(echo_tool()),
            model=model,
            config=self.config(),
        )
        result = harness.run("在吗")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.text, "收到")
        self.assertEqual(result.turns, 2)
        self.assertEqual(result.tool_calls, 1)
        self.assertIsNotNone(result.trace_path)
        self.assertTrue(result.trace_path.exists())

        results = tool_results(result.messages)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].get("is_error", False))
        self.assertEqual(json.loads(results[0]["content"]), {"echo": "你好"})

        events = load_events(result.trace_path)
        types = [event["type"] for event in events]
        self.assertIn("run.started", types)
        self.assertIn("tool.call", types)
        self.assertIn("tool.result", types)
        self.assertEqual(types[-1], "run.finished")
        self.assertIn("🧾", render_events(events))

    def test_unknown_tool_becomes_tool_error(self) -> None:
        model = ScriptedModel([call("nope", x=1), say("我换一个工具")])
        harness = Harness(agent=make_agent(echo_tool()), model=model, config=self.config())
        result = harness.run("试试")

        self.assertEqual(result.status, "ok")
        results = tool_results(result.messages)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_error"])
        self.assertIn("未知工具", results[0]["content"])

    def test_tool_error_is_returned_to_model(self) -> None:
        model = ScriptedModel([call("fail"), say("没有珍珠了，换椰果可以吗？")])
        harness = Harness(agent=make_agent(failing_tool()), model=model, config=self.config())
        result = harness.run("来杯珍珠")

        self.assertEqual(result.status, "ok")
        results = tool_results(result.messages)
        self.assertTrue(results[0]["is_error"])
        self.assertIn("缺珍珠了", results[0]["content"])

    def test_unexpected_tool_exception_is_caught(self) -> None:
        model = ScriptedModel([call("crash"), say("设备坏了")])
        harness = Harness(agent=make_agent(crashing_tool()), model=model, config=self.config())
        result = harness.run("开机")

        self.assertEqual(result.status, "ok")
        self.assertTrue(tool_results(result.messages)[0]["is_error"])
        event_types = [event["type"] for event in result.events]
        self.assertIn("tool.error", event_types)

    def test_guardrail_denies_before_tool_runs(self) -> None:
        executed: list[dict[str, Any]] = []

        def handler(ctx, arguments):
            executed.append(arguments)
            return {"ok": True}

        guarded = Tool(
            name="danger",
            description="危险操作",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=handler,
        )

        class ManagerRule:
            def check(self, *, tool, arguments, ctx):
                return "店长守则：今天不卖这一单"

        model = ScriptedModel([call("danger"), say("好的，我换个方案")])
        harness = Harness(
            agent=make_agent(guarded),
            model=model,
            config=self.config(),
            guardrails=[ManagerRule()],
        )
        result = harness.run("来一杯")

        self.assertEqual(executed, [])
        self.assertTrue(tool_results(result.messages)[0]["is_error"])
        self.assertIn("店长守则", tool_results(result.messages)[0]["content"])
        self.assertIn("guardrail.denied", [event["type"] for event in result.events])

    def test_max_turns_stops_loop(self) -> None:
        model = ScriptedModel([call("echo"), call("echo"), call("echo"), say("结束")])
        harness = Harness(
            agent=make_agent(echo_tool()),
            model=model,
            config=self.config(max_turns=2),
        )
        result = harness.run("循环吧")

        self.assertEqual(result.status, "max_turns")
        self.assertEqual(result.turns, 2)
        self.assertIn("harness.stopped", [event["type"] for event in result.events])

    def test_max_tool_calls_keeps_message_history_valid(self) -> None:
        model = ScriptedModel(
            [
                turn(tool_use_block("echo", text="a"), tool_use_block("echo", text="b")),
                say("结束"),
            ]
        )
        harness = Harness(
            agent=make_agent(echo_tool()),
            model=model,
            config=self.config(max_tool_calls=1),
        )
        result = harness.run("并行两件")

        self.assertEqual(result.status, "max_tool_calls")
        self.assertEqual(result.tool_calls, 1)
        results = tool_results(result.messages)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[1]["is_error"])

        # 每个 tool_use 都必须有配对的 tool_result，否则会话无法继续。
        tool_use_ids = [
            block["id"]
            for message in result.messages
            for block in message.get("content", [])
            if block.get("type") == "tool_use"
        ]
        result_ids = [block["tool_use_id"] for block in results]
        self.assertEqual(tool_use_ids, result_ids)

    def test_session_continues_across_runs(self) -> None:
        model = ScriptedModel([say("第一单"), say("第二单")])
        harness = Harness(agent=make_agent(echo_tool()), model=model, config=self.config())
        session = Session()

        first = harness.run("你好", session=session)
        second = harness.run("再来", session=session)

        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual(len(second.messages), 4)
        self.assertEqual(second.text, "第二单")

    def test_on_event_receives_events(self) -> None:
        seen: list[str] = []
        harness = Harness(
            agent=make_agent(echo_tool()),
            model=ScriptedModel([say("好")]),
            config=self.config(),
            on_event=lambda event: seen.append(event["type"]),
        )
        harness.run("你好")
        self.assertIn("run.started", seen)
        self.assertIn("run.finished", seen)


class ScriptedModelTest(unittest.TestCase):
    def test_assigns_unique_tool_ids(self) -> None:
        model = ScriptedModel([call("echo"), call("echo")])
        agent = make_agent(echo_tool())
        first = model.generate(system="", messages=[], tools=agent.tools)
        second = model.generate(system="", messages=[], tools=agent.tools)
        self.assertNotEqual(
            first.tool_calls[0].id,
            second.tool_calls[0].id,
        )

    def test_exhausted_script_ends_gracefully(self) -> None:
        model = ScriptedModel([], fallback_text="打烊了")
        turn_result = model.generate(system="", messages=[], tools=[])
        self.assertEqual(turn_result.text, "打烊了")
        self.assertEqual(turn_result.stop_reason, "end_turn")


if __name__ == "__main__":
    unittest.main()
