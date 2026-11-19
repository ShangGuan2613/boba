"""Lesson 06 · eval：用固定用例回归，不靠“我觉得修好了”。

每个 case 是一段固定输入 + 期望的收尾状态。Trace 是证据，
eval 把证据变成可重复的通过 / 失败。
"""

from __future__ import annotations

from dataclasses import dataclass

from boba.trace import Trace


@dataclass(frozen=True)
class EvalCase:
    name: str
    expected_status: str
    trace: Trace


@dataclass(frozen=True)
class EvalResult:
    name: str
    ok: bool
    expected: str
    actual: str


def run_eval(cases: list[EvalCase]) -> list[EvalResult]:
    results = []
    for case in cases:
        actual = case.trace.status()
        results.append(
            EvalResult(
                name=case.name,
                ok=actual == case.expected_status,
                expected=case.expected_status,
                actual=actual,
            )
        )
    return results


def demo() -> None:
    ok_trace = Trace("run_ok")
    ok_trace.emit("run.start")
    ok_trace.emit("run.end", status="ok")

    bad_trace = Trace("run_bad")
    bad_trace.emit("run.start")
    bad_trace.emit("tool.call", tool="order_create", quantity=20)
    bad_trace.emit("run.end", status="permission_denied")

    for result in run_eval(
        [
            EvalCase("正常下单", "ok", ok_trace),
            EvalCase("超量被拦", "permission_denied", bad_trace),
        ]
    ):
        mark = "PASS" if result.ok else "FAIL"
        print(f"{mark}  {result.name}  期望={result.expected}  实际={result.actual}")


if __name__ == "__main__":
    demo()
