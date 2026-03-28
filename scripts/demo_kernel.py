#!/usr/bin/env python3
"""Demo script showing basic Agent OS Kernel usage.

Run from the project root:
    uv run python scripts/demo_kernel.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.process import ProcessProvider
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)


def main() -> None:
    # Create a temporary workspace
    with tempfile.TemporaryDirectory() as workspace:
        ws = Path(workspace)
        (ws / "output").mkdir()
        (ws / "data.txt").write_text("Hello from the workspace!")

        # Write a policy file
        policy_path = ws / "policy.yaml"
        policy_path.write_text(
            f"""capabilities:
  - action: fs.read
    resource: {workspace}/**
  - action: fs.write
    resource: {workspace}/output/**
  - action: fs.delete
    resource: {workspace}/output/**
  - action: proc.exec
    resource: echo
"""
        )

        log_path = ws / "kernel.log"

        # --- Basic Kernel Usage ---
        print("=== Basic Kernel Usage ===\n")

        with Kernel(
            policy=str(policy_path),
            providers=[FilesystemProvider(), ProcessProvider()],
            log_path=str(log_path),
        ) as kernel:
            # 1. Allowed read
            result = kernel.submit(ActionRequest(action="fs.read", target=str(ws / "data.txt")))
            print(f"Read result:  status={result.status}, data={result.data!r}")

            # 2. Allowed write
            out_file = ws / "output" / "report.txt"
            result = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(out_file),
                    params={"content": "Generated report"},
                )
            )
            print(f"Write result: status={result.status}, data={result.data}")

            # 3. Denied action (writing outside allowed path)
            result = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target="/etc/passwd",
                    params={"content": "hacked"},
                )
            )
            print(f"Denied write: status={result.status}, error={result.error}")

            # 4. Process execution
            result = kernel.submit(ActionRequest(action="proc.exec", target="echo", params={"args": ["hello"]}))
            print(f"Proc result:  status={result.status}, stdout={result.data['stdout'].strip()!r}")

            # 5. Check audit log
            records = kernel.log.read_all()
            print(f"\nAudit log: {len(records)} entries")
            for r in records:
                print(f"  [{r.status}] {r.action} -> {r.target}")

        # --- Reversible Layer ---
        print("\n=== Reversible Action Layer ===\n")

        with Kernel(
            policy=str(policy_path),
            providers=[FilesystemProvider()],
            log_path=str(ws / "kernel2.log"),
        ) as kernel:
            store = SnapshotStore(str(ws / ".snapshots"))
            layer = ReversibleActionLayer(
                kernel=kernel,
                strategies=[FsWriteSnapshotStrategy()],
                store=store,
            )

            target_file = ws / "output" / "important.txt"
            target_file.write_text("original content")

            # Write through the layer
            result = layer.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(target_file),
                    params={"content": "OVERWRITTEN BY AGENT"},
                )
            )
            print(f"Write: status={result.status}, record_id={result.record_id}")
            print(f"File now: {target_file.read_text()!r}")

            # Roll back
            if result.record_id:
                rollback = layer.rollback(result.record_id)
                print(f"Rollback: status={rollback.status}")
                print(f"File now: {target_file.read_text()!r}")

    print("\nDone!")


if __name__ == "__main__":
    main()
