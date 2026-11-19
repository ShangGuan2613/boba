"""核心类型：一单生意里最小的协作单元。

Harness 只认识这里的类型，不认识“奶茶”。
奶茶店是第一个租户，不是框架本身。

术语映射：
- Agent    = 店员（配方卡 + 技能 + 模型）
- Tool     = 设备/工位
- Model    = 茶底/原料
- Guardrail= 店长守则
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

__all__ = [
    "Agent",
    "BobaError",
    "Guardrail",
    "Model",
    "ModelTurn",
    "Tool",
    "ToolCall",
    "ToolContext",
    "ToolError",
    "ModelError",
    "call",
    "say",
    "text_block",
    "tool_result_block",
    "tool_use_block",
    "turn",
]

_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class BobaError(Exception):
    """boba 的可预期错误基类。"""


class ToolError(BobaError):
    """工具执行失败。

    错误信息会作为 ``tool_result`` 交还给模型，因此应当写成
    模型能读懂、能据此改正的中文短句。
    """


class ModelError(BobaError):
    """模型调用失败。"""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelTurn:
    """模型的一次回复，使用与 Anthropic Messages API 一致的 content block 形状。"""

    content: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"

    @property
    def text(self) -> str:
        return "".join(
            str(block.get("text", ""))
            for block in self.content
            if block.get("type") == "text"
        ).strip()

    @property
    def tool_calls(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for block in self.content:
            if block.get("type") != "tool_use":
                continue
            calls.append(
                ToolCall(
                    id=str(block.get("id", "")),
                    name=str(block.get("name", "")),
                    arguments=dict(block.get("input") or {}),
                )
            )
        return calls


@dataclass
class ToolContext:
    """工具运行时拿到的上下文。

    ``resources`` 由应用注入（例如奶茶店的 ``shop``），Harness 本身不解释它。
    """

    run_id: str
    session_id: str
    resources: Mapping[str, Any]
    emit: Callable[[str, dict[str, Any]], None]

    def resource(self, name: str) -> Any:
        try:
            return self.resources[name]
        except KeyError as exc:
            raise KeyError(f"未注册的资源: {name}") from exc


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], Any]
    label: str = ""

    def __post_init__(self) -> None:
        if not _TOOL_NAME_RE.match(self.name):
            raise ValueError(
                f"工具名 {self.name!r} 不合法：只允许字母、数字、下划线和连字符，长度 1-64"
            )
        if self.input_schema.get("type") != "object":
            raise ValueError(f"工具 {self.name!r} 的 input_schema 必须是 object")

    def spec(self) -> dict[str, Any]:
        """转成模型 API 需要的工具声明。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class Guardrail(Protocol):
    """店长守则：在工具执行前检查，返回拒绝理由或 None。"""

    def check(
        self, *, tool: Tool, arguments: dict[str, Any], ctx: ToolContext
    ) -> str | None: ...


class Model(Protocol):
    """茶底/原料：把会话变成下一次 ModelTurn。"""

    name: str
    label: str

    def generate(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[Tool],
    ) -> ModelTurn: ...


@dataclass
class Agent:
    """店员：配方卡（system prompt）+ 技能（tools）。"""

    name: str
    system_prompt: str
    tools: Sequence[Tool]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Agent.name 不能为空")
        if not self.system_prompt.strip():
            raise ValueError("Agent.system_prompt 不能为空")
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError(f"Agent {self.name!r} 注册了重名工具: {names}")


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def tool_use_block(name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": "", "name": name, "input": arguments}


def tool_result_block(
    tool_use_id: str, content: str, *, is_error: bool = False
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }
    if is_error:
        block["is_error"] = True
    return block


def turn(*blocks: dict[str, Any], stop_reason: str = "tool_use") -> ModelTurn:
    """把若干 content block 组成一次模型回复。"""
    return ModelTurn(content=list(blocks), stop_reason=stop_reason)


def say(text: str) -> ModelTurn:
    return ModelTurn(content=[text_block(text)], stop_reason="end_turn")


def call(name: str, **arguments: Any) -> ModelTurn:
    """构造一次“只调用工具”的模型回复，供离线脚本模型使用。"""
    return ModelTurn(
        content=[tool_use_block(name, **arguments)], stop_reason="tool_use"
    )
