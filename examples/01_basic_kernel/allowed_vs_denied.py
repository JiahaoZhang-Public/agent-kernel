#!/usr/bin/env python3
"""Show OK vs DENIED side by side.

Demonstrates the default-deny policy: a read against /workspace/** succeeds,
while a read against /etc/passwd is denied by the Gate.

Run:
    uv run python examples/01_basic_kernel/allowed_vs_denied.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import print_result

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("Allowed content inside the workspace.")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as kernel:
            # 1. Allowed read
            print("[1] fs.read inside workspace (should be OK):")
            r1 = kernel.submit(ActionRequest(action="fs.read", target=str(workspace / "notes.txt")))
            print_result(r1)

            print()

            # 2. Denied read
            print("[2] fs.read /etc/passwd (should be DENIED):")
            r2 = kernel.submit(ActionRequest(action="fs.read", target="/etc/passwd"))
            print_result(r2)


if __name__ == "__main__":
    main()
