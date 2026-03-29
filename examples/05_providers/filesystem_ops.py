"""Filesystem provider example — read, write, delete.

Demonstrates all three actions supported by FilesystemProvider:
fs.read, fs.write, and fs.delete, routed through the Kernel gate.

Run:
    python -m examples.05_providers.filesystem_ops
    # or
    python examples/05_providers/filesystem_ops.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log, print_result


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Broad policy: allow all fs operations within workspace
        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/**"),
            ]
        )

        # Seed a file
        sample_file = workspace / "hello.txt"
        sample_file.write_text("Hello, Agent OS Kernel!\n")

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            # -- fs.read -------------------------------------------------------
            print("1) fs.read — read a file")
            r1 = kernel.submit(
                ActionRequest(
                    action="fs.read",
                    target=str(sample_file),
                )
            )
            print_result(r1)
            print()

            # -- fs.write ------------------------------------------------------
            print("2) fs.write — create a new file")
            output_file = workspace / "output" / "report.txt"
            r2 = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(output_file),
                    params={"content": "Quarterly report data.\nRow 1: OK\nRow 2: OK\n"},
                )
            )
            print_result(r2)
            # Verify the file exists
            assert output_file.exists(), "Written file should exist"
            print(f"  verified  : file exists at {output_file}")
            print()

            # -- fs.read the written file back ---------------------------------
            print("3) fs.read — read back the written file")
            r3 = kernel.submit(
                ActionRequest(
                    action="fs.read",
                    target=str(output_file),
                )
            )
            print_result(r3)
            print()

            # -- fs.delete -----------------------------------------------------
            print("4) fs.delete — remove the file")
            r4 = kernel.submit(
                ActionRequest(
                    action="fs.delete",
                    target=str(output_file),
                )
            )
            print_result(r4)
            # Verify the file is gone
            assert not output_file.exists(), "Deleted file should not exist"
            print("  verified  : file removed")
            print()

            # -- fs.read a deleted file -> ERROR -------------------------------
            print("5) fs.read — attempt to read deleted file (ERROR)")
            r5 = kernel.submit(
                ActionRequest(
                    action="fs.read",
                    target=str(output_file),
                )
            )
            print_result(r5)
            print()

        # -- Audit log ---------------------------------------------------------
        print("=" * 60)
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
