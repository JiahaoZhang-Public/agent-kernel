"""Reversible Action Layer for the Agent OS Kernel (v2.1).

Per v2.1 design: this layer sits between the agent loop and the kernel,
wrapping kernel.submit() without modifying it. Rollback actions go through
the Gate — they are authorized and logged like any other action.

Three new components:
- SnapshotStrategy: captures pre-execution state
- SnapshotStore: persists snapshots with TTL
- ReversibleActionLayer: coordinates snapshot capture, execution, and rollback
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest, ActionResult

logger = logging.getLogger(__name__)


class SnapshotStrategy(ABC):
    """Captures pre-execution state for a specific action type.

    Each provider that supports rollback defines its own strategy.
    """

    @abstractmethod
    def supports(self, request: ActionRequest) -> bool:
        """Whether this strategy can snapshot the given request."""
        ...

    @abstractmethod
    def capture(self, request: ActionRequest) -> Any:
        """Capture state before execution. Returns opaque snapshot data."""
        ...

    @abstractmethod
    def restore(self, request: ActionRequest, snapshot: Any) -> ActionRequest:
        """Build a restore ActionRequest from the snapshot.

        The returned ActionRequest will be submitted through the kernel
        like any other action — authorized and logged.
        """
        ...


class FsWriteSnapshotStrategy(SnapshotStrategy):
    """Snapshot strategy for fs.write actions.

    Captures file content before overwrite so it can be restored.
    """

    def supports(self, request: ActionRequest) -> bool:
        return request.action == "fs.write"

    def capture(self, request: ActionRequest) -> dict[str, Any]:
        path = Path(request.target)
        if path.exists():
            return {"existed": True, "content": path.read_text()}
        return {"existed": False}

    def restore(self, request: ActionRequest, snapshot: dict[str, Any]) -> ActionRequest:
        if snapshot["existed"]:
            return ActionRequest(
                action="fs.write",
                target=request.target,
                params={"content": snapshot["content"]},
            )
        else:
            return ActionRequest(
                action="fs.delete",
                target=request.target,
                params={},
            )


class FsDeleteSnapshotStrategy(SnapshotStrategy):
    """Snapshot strategy for fs.delete actions.

    Captures file content before deletion so it can be restored via fs.write.
    If the file did not exist before delete, capture returns None and no
    snapshot is persisted (the delete was a no-op, nothing to restore).
    """

    def supports(self, request: ActionRequest) -> bool:
        return request.action == "fs.delete"

    def capture(self, request: ActionRequest) -> dict[str, Any] | None:
        path = Path(request.target)
        if path.exists():
            return {"content": path.read_text()}
        return None

    def restore(self, request: ActionRequest, snapshot: dict[str, Any]) -> ActionRequest:
        return ActionRequest(
            action="fs.write",
            target=request.target,
            params={"content": snapshot["content"]},
        )


class SnapshotStore:
    """Persists snapshots indexed by record ID.

    A simple file-based key-value store. Snapshots expire after TTL.
    """

    def __init__(self, store_dir: str | Path, ttl_seconds: int = 3600) -> None:
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._ttl_seconds = ttl_seconds

    def save(self, record_id: str, request: ActionRequest, snapshot: Any) -> None:
        """Save a snapshot associated with a record ID."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        entry = {
            "record_id": record_id,
            "original_request": {
                "action": request.action,
                "target": request.target,
                "params": request.params,
            },
            "snapshot": snapshot,
            "created_at": now.isoformat(),
            "expires_at": (datetime.fromtimestamp(now.timestamp() + self._ttl_seconds, tz=timezone.utc)).isoformat(),
        }
        path = self._store_dir / f"{record_id}.json"
        path.write_text(json.dumps(entry))

    def load(self, record_id: str) -> tuple[ActionRequest, Any] | None:
        """Load a snapshot by record ID. Returns None if not found or expired."""
        from datetime import datetime, timezone

        path = self._store_dir / f"{record_id}.json"
        if not path.exists():
            return None

        entry = json.loads(path.read_text())

        # Check TTL via expires_at (preferred) or created_at (legacy)
        if "expires_at" in entry:
            expires_at = datetime.fromisoformat(entry["expires_at"])
            if datetime.now(timezone.utc) >= expires_at:
                path.unlink(missing_ok=True)
                return None
        elif "created_at" in entry:
            # Legacy format: created_at as float
            created = entry["created_at"]
            if isinstance(created, int | float) and time.time() - created > self._ttl_seconds:
                path.unlink(missing_ok=True)
                return None

        # Support both new ("original_request") and legacy ("request") key
        req_data = entry.get("original_request") or entry["request"]
        request = ActionRequest(
            action=req_data["action"],
            target=req_data["target"],
            params=req_data["params"],
        )
        return request, entry["snapshot"]

    def delete(self, record_id: str) -> None:
        """Remove a snapshot after successful rollback."""
        path = self._store_dir / f"{record_id}.json"
        path.unlink(missing_ok=True)


class ReversibleActionLayer:
    """Wraps the kernel to provide snapshot-based rollback.

    The layer coordinates snapshot capture, execution, and rollback.
    The kernel does not know this layer exists.
    """

    def __init__(
        self,
        kernel: Kernel,
        strategies: list[SnapshotStrategy],
        store: SnapshotStore,
    ) -> None:
        self.kernel = kernel
        self.strategies = strategies
        self.store = store

    def submit(self, request: ActionRequest) -> ActionResult:
        """Submit an action, capturing a snapshot if the action is reversible.

        Per design §7.1-7.2: capture and persistence failures are best-effort.
        If either fails, the action proceeds without rollback capability.

        Note: record_id is set on the returned ActionResult, not on the
        kernel's log Record. See Record.record_id docstring for rationale.
        """
        # 1. Find a matching snapshot strategy
        strategy = self._find_strategy(request)

        # 2. Capture snapshot before execution (best-effort per §7.1)
        snapshot = None
        if strategy is not None:
            try:
                snapshot = strategy.capture(request)
            except Exception:
                logger.warning(
                    "Snapshot capture failed for %s:%s",
                    request.action,
                    request.target,
                    exc_info=True,
                )
                snapshot = None

        # 3. Execute through the kernel
        result = self.kernel.submit(request)

        # 4. If execution succeeded and we have a snapshot, persist it (best-effort per §7.2)
        if result.status == "OK" and snapshot is not None:
            record_id = self._generate_record_id()
            try:
                self.store.save(record_id, request, snapshot)
                result.record_id = record_id
            except Exception:
                logger.warning(
                    "Failed to save snapshot for %s:%s",
                    request.action,
                    request.target,
                    exc_info=True,
                )

        return result

    def rollback(self, record_id: str) -> ActionResult:
        """Roll back a previously executed action by its record ID."""
        # 1. Load the snapshot
        entry = self.store.load(record_id)
        if entry is None:
            return ActionResult(status="ERROR", data=None, error="no snapshot found")

        original_request, snapshot = entry

        # 2. Find the strategy that created this snapshot
        strategy = self._find_strategy(original_request)
        if strategy is None:
            return ActionResult(status="ERROR", data=None, error="no strategy for action type")

        # 3. Build the restore request
        restore_request = strategy.restore(original_request, snapshot)

        # 4. Submit the restore through the kernel (authorized + logged)
        result = self.kernel.submit(restore_request)

        # 5. Clean up the snapshot on success
        if result.status == "OK":
            self.store.delete(record_id)

        return result

    def _find_strategy(self, request: ActionRequest) -> SnapshotStrategy | None:
        for strategy in self.strategies:
            if strategy.supports(request):
                return strategy
        return None

    def _generate_record_id(self) -> str:
        return uuid4().hex
