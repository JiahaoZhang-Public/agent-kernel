#!/usr/bin/env python3
"""Write-and-rollback lifecycle: overwrite a file, then restore the original.

Demonstrates the core ReversibleActionLayer flow:
1. Create a file with original content
2. Overwrite it via layer.submit() (snapshot captured automatically)
3. Roll back using the record_id from the result
4. Verify the original content is restored

No LLM required.

Run:
    uv run python examples/04_reversible/write_and_rollback.py
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

        # Seed a file with original content
        target = workspace / "notes.txt"
        target.write_text("original content")

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
                strategies=[FsWriteSnapshotStrategy()],
                store=SnapshotStore(str(snapshot_dir)),
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
            print(f"File now     : {target.read_text()!r}")

            assert result.record_id is not None, "Expected a record_id for reversible write"

            # Roll back to original
            rollback_result = layer.rollback(result.record_id)
            print(f"\nRollback status : {rollback_result.status}")
            print(f"File restored   : {target.read_text()!r}")

            assert target.read_text() == "original content", "Rollback did not restore original"
            print("\nSuccess: file restored to original content.")


if __name__ == "__main__":
    main()
