#!/usr/bin/env python3
"""Rollback of a write that created a new file (file did not exist before).

FsWriteSnapshotStrategy captures {"existed": False} when the target file
does not exist. On rollback, it generates an fs.delete action instead of
fs.write, removing the file that was created.

No LLM required.

Run:
    uv run python examples/04_reversible/new_file_rollback.py
"""

from __future__ import annotations

import tempfile
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

        # Target file does NOT exist yet
        target = workspace / "brand_new.txt"
        assert not target.exists(), "File should not exist before the test"

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.write", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as kernel:
            layer = ReversibleActionLayer(
                kernel=kernel,
                strategies=[FsWriteSnapshotStrategy()],
                store=SnapshotStore(str(snapshot_dir)),
            )

            # Create a new file via fs.write
            result = layer.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(target),
                    params={"content": "newly created content"},
                )
            )
            print(f"Write status : {result.status}")
            print(f"Record ID    : {result.record_id}")
            print(f"File exists  : {target.exists()}")
            print(f"File content : {target.read_text()!r}")

            assert target.exists(), "File should exist after write"

            # Roll back — should DELETE the file (not overwrite with empty)
            assert result.record_id is not None
            rollback_result = layer.rollback(result.record_id)
            print(f"\nRollback status : {rollback_result.status}")
            print(f"File exists     : {target.exists()}")

            assert not target.exists(), "File should not exist after rollback of new-file write"
            print("\nSuccess: new file removed by rollback (fs.delete generated).")


if __name__ == "__main__":
    main()
