#!/usr/bin/env python3
"""Snapshot TTL expiry: rollback fails after the snapshot expires.

Demonstrates SnapshotStore TTL — a short ttl_seconds causes the snapshot
to expire, making rollback impossible after the window closes.

No LLM required.

Run:
    uv run python examples/04_reversible/snapshot_expiry.py
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        snapshot_dir = Path(tmp) / "snapshots"

        target = workspace / "ephemeral.txt"
        target.write_text("original")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.write", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as kernel:
            # Store with a 2-second TTL
            store = SnapshotStore(str(snapshot_dir), ttl_seconds=2)
            layer = ReversibleActionLayer(
                kernel=kernel,
                strategies=[FsWriteSnapshotStrategy()],
                store=store,
            )

            # Overwrite the file
            result = layer.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(target),
                    params={"content": "OVERWRITTEN"},
                )
            )
            print(f"Write status : {result.status}")
            print(f"Record ID    : {result.record_id}")

            # Wait for the snapshot to expire
            print("\nWaiting 3 seconds for snapshot to expire...")
            time.sleep(3)

            # Attempt rollback — should fail
            assert result.record_id is not None
            rollback_result = layer.rollback(result.record_id)
            print(f"Rollback status : {rollback_result.status}")
            print(f"Rollback error  : {rollback_result.error}")

            assert rollback_result.status == "ERROR", "Expected rollback to fail"
            assert rollback_result.error == "no snapshot found", "Expected 'no snapshot found' error"
            print("\nSuccess: rollback correctly rejected after TTL expiry.")


if __name__ == "__main__":
    main()
