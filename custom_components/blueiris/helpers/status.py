"""Helpers for Blue Iris status data."""

from __future__ import annotations


def parse_uptime(value: str) -> int | None:
    """Convert Blue Iris D:HH:MM:SS uptime to seconds."""
    parts = value.split(":")

    if len(parts) != 4:
        return None

    try:
        days, hours, minutes, seconds = map(int, parts)
    except ValueError:
        return None

    return (
        days * 86400
        + hours * 3600
        + minutes * 60
        + seconds
    )