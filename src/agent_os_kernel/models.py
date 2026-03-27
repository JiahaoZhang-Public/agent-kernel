"""Core object model for the Agent OS Kernel.

Defines ActionRequest, ActionResult, and Record per v2 design §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionRequest:
    """A request to perform a world-facing action.

    Attributes:
        action: Action type, e.g. "fs.read", "net.http".
        target: Resource target, e.g. "/workspace/data.csv".
        params: Action-specific parameters.
    """

    action: str
    target: str
    params: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> bool:
        """Check that the request has required fields and valid format."""
        return bool(self.action and self.target)


@dataclass
class ActionResult:
    """The result of a submitted action.

    Attributes:
        status: One of "OK", "DENIED", "ERROR".
        data: Provider return value, or None.
        error: Error message if status is not OK.
        record_id: Optional snapshot ID for reversible actions (v2.1).
    """

    status: str
    data: Any = None
    error: str | None = None
    record_id: str | None = None


@dataclass
class Record:
    """An append-only log entry produced by every Gate decision.

    Attributes:
        timestamp: ISO 8601 timestamp.
        action: Action type, e.g. "fs.read".
        target: Resource target.
        status: One of "INVALID", "DENIED", "NO_PROVIDER", "FAILED", "OK".
        error: Error message if status is not OK.
        duration_ms: Execution time if provider was called.
        record_id: Optional snapshot ID linking to reversible action (v2.1).
    """

    timestamp: str
    action: str
    target: str
    status: str
    error: str | None = None
    duration_ms: int | None = None
    record_id: str | None = None
