#!/usr/bin/env python3
"""Delete-and-rollback: delete a file, then restore it via rollback.

Demonstrates FsDeleteSnapshotStrategy — the snapshot captures file content
before deletion so rollback can recreate it via fs.write. The policy must
allow both fs.write and fs.delete on the workspace because rollback of a
delete produces a write action.

No LLM required.

Run:
    uv run python examples/04_reversible/delete_and_rollback.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.reversible import (
    FsDeleteSnapshotStrategy,
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        snapshot_dir = Path(tmp) / "snapshots"

        # Seed a file to be deleted
        target = workspace / "important.txt"
        target.write_text("precious data that must not be lost")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as kernel:
            layer = ReversibleActionLayer(
                kernel=kernel,
                strategies=[FsWriteSnapshotStrategy(), FsDeleteSnapshotStrategy()],
                store=SnapshotStore(str(snapshot_dir)),
            )

            # Delete the file
            result = layer.submit(
                ActionRequest(
                    action="fs.delete",
                    target=str(target),
                    params={},
                )
            )
            print(f"Delete status : {result.status}")
            print(f"Record ID     : {result.record_id}")
            print(f"File exists   : {target.exists()}")

            assert not target.exists(), "File should be gone after delete"

            # Roll back the deletion
            assert result.record_id is not None
            rollback_result = layer.rollback(result.record_id)
            print(f"\nRollback status : {rollback_result.status}")
            print(f"File exists     : {target.exists()}")
            print(f"File content    : {target.read_text()!r}")

            assert target.exists(), "File should be restored after rollback"
            assert target.read_text() == "precious data that must not be lost"
            print("\nSuccess: deleted file restored via rollback.")


if __name__ == "__main__":
    main()
