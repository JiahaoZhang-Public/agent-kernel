#!/usr/bin/env python3
"""Submit 5 mixed actions, then read and print the audit log.

Demonstrates the kernel's append-only logging: every submit() call
produces exactly one log record, regardless of outcome.

Run:
    uv run python examples/01_basic_kernel/audit_log_inspection.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import print_audit_log

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.process import ProcessProvider


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        (workspace / "output").mkdir()
        (workspace / "data.txt").write_text("sample data for audit demo")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/output/**"),
                CapabilityRule(action="proc.exec", resource="echo"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider(), ProcessProvider()],
            log_path=log_path,
        ) as kernel:
            # 1. OK — read a file
            kernel.submit(ActionRequest(action="fs.read", target=str(workspace / "data.txt")))

            # 2. OK — write a file
            kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(workspace / "output" / "result.txt"),
                    params={"content": "hello from audit demo"},
                )
            )

            # 3. DENIED — read outside workspace
            kernel.submit(ActionRequest(action="fs.read", target="/etc/passwd"))

            # 4. OK — run echo
            kernel.submit(ActionRequest(action="proc.exec", target="echo", params={"args": ["audit", "test"]}))

            # 5. DENIED — delete not allowed by policy
            kernel.submit(ActionRequest(action="fs.delete", target=str(workspace / "data.txt")))

        # ── Print the audit log ───────────────────────────────────────
        print("Audit log entries:")
        print()
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
