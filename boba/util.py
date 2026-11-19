"""小工具：时间、金额、文本裁剪。"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """RFC 3339 时间戳，例如 2026-11-19T10:00:00.000Z。"""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def yuan(cents: int) -> int | float:
    """分 -> 元。整数金额返回 int，避免 JSON 里出现 12.0。"""
    value = cents / 100
    return int(value) if value.is_integer() else round(value, 2)


def money(cents: int) -> str:
    """分 -> 展示用金额，例如 ¥24、¥12.50。"""
    if cents % 100 == 0:
        return f"¥{cents // 100}"
    return f"¥{cents / 100:.2f}"


def clip(text: object, limit: int = 100) -> str:
    """压成单行并截断，用于日志和终端展示。"""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
