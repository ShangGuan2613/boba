from __future__ import annotations

import unittest
from types import SimpleNamespace

from boba.core import Tool, call
from boba.models import AnthropicModel, ScriptedModel


def demo_tool() -> Tool:
    return Tool(
        name="echo",
        description="原样返回",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=lambda ctx, arguments: arguments,
    )


class FakeMessages:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response) -> None:
        self.messages = FakeMessages(response)


def response_with(content, stop_reason="end_turn", category=None):
    details = SimpleNamespace(category=category) if category else None
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=details,
    )


class AnthropicModelTest(unittest.TestCase):
    def test_maps_request_and_response(self) -> None:
        response = response_with(
            [
                SimpleNamespace(type="thinking", thinking="先想一下", signature="sig"),
                SimpleNamespace(type="text", text="你好呀"),
                SimpleNamespace(
                    type="tool_use",
                    id="call_1",
                    name="echo",
                    input={"text": "hi"},
                ),
                SimpleNamespace(type="fallback", from_=None, to=None),
            ],
            stop_reason="tool_use",
        )
        client = FakeClient(response)
        model = AnthropicModel(client=client, fallbacks=False)

        turn = model.generate(
            system="配方卡",
            messages=[{"role": "user", "content": "hi"}],
            tools=[demo_tool()],
        )

        kwargs = client.messages.kwargs
        self.assertEqual(kwargs["model"], "claude-opus-5-5")
        self.assertEqual(kwargs["thinking"], {"type": "adaptive"})
        self.assertEqual(kwargs["output_config"], {"effort": "medium"})
        self.assertEqual(kwargs["tools"][0]["name"], "echo")
        self.assertEqual(kwargs["system"], "配方卡")

        self.assertEqual(turn.text, "你好呀")
        self.assertEqual(turn.stop_reason, "tool_use")
        self.assertEqual(turn.tool_calls[0].name, "echo")
        self.assertEqual(turn.tool_calls[0].arguments, {"text": "hi"})
        self.assertEqual(
            [block["type"] for block in turn.content],
            ["thinking", "text", "tool_use"],
        )

    def test_refusal_is_reported(self) -> None:
        client = FakeClient(
            response_with([], stop_reason="refusal", category="cyber")
        )
        model = AnthropicModel(client=client, fallbacks=False)
        turn = model.generate(system="s", messages=[], tools=[])

        self.assertEqual(turn.stop_reason, "refusal")
        self.assertIn("无法处理", turn.text)
        self.assertIn("cyber", turn.text)

    def test_empty_response_gets_placeholder(self) -> None:
        client = FakeClient(response_with([]))
        model = AnthropicModel(client=client, fallbacks=False)
        turn = model.generate(system="s", messages=[], tools=[])
        self.assertEqual(turn.text, "（模型没有返回内容）")

    def test_invalid_effort_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AnthropicModel(client=FakeClient(response_with([])), effort="turbo")

    def test_without_sdk_and_client_raises_helpful_error(self) -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            with self.assertRaisesRegex(RuntimeError, "boba\\[anthropic\\]"):
                AnthropicModel()
        else:
            self.skipTest("anthropic 已安装，跳过缺依赖测试")


class ScriptedModelTest(unittest.TestCase):
    def test_callable_step_reads_messages(self) -> None:
        def step(messages):
            return call("echo", text=str(len(messages)))

        model = ScriptedModel([step])
        turn = model.generate(system="", messages=[{"role": "user", "content": []}], tools=[])
        self.assertEqual(turn.tool_calls[0].arguments, {"text": "1"})


if __name__ == "__main__":
    unittest.main()
