"""Camera data model used by the coordinator snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CameraData:
    """Normalized camera snapshot from Blue Iris camlist.

    The coordinator stores instances of this dataclass so platform code can use
    a stable, normalized view of Blue Iris camera metadata without repeatedly
    interpreting the raw camlist payload.
    """
    data: dict[str, Any]  # raw BI dict (kept for diagnostics/debug)
    id: str
    name: str
    has_audio: bool
    is_online: bool
    is_active: bool
    is_enabled: bool
    group_cameras: list[str] | None  # list for groups, None for non-groups
    is_system: bool
    type: int
