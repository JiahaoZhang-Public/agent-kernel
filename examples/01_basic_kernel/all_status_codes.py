#!/usr/bin/env python3
"""Demonstrate all four kernel status paths: OK, DENIED, NO_PROVIDER, INVALID.

Each submit() call follows a different path through the Gate, showing how
the kernel handles every possible outcome.

Run:
    uv run python examples/01_basic_kernel/all_status_codes.py
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
        (workspace / "file.txt").write_text("kernel status demo")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="net.http", resource="https://example.com/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        # Only register FilesystemProvider — no HttpProvider
        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as kernel:
            # 1. OK — valid read inside workspace
            print("[1] OK — fs.read inside workspace:")
            r1 = kernel.submit(ActionRequest(action="fs.read", target=str(workspace / "file.txt")))
            print_result(r1)
            print()

            # 2. DENIED — read outside workspace
            print("[2] DENIED — fs.read outside workspace:")
            r2 = kernel.submit(ActionRequest(action="fs.read", target="/etc/shadow"))
            print_result(r2)
            print()

            # 3. NO_PROVIDER — net.http is allowed by policy but no provider registered
            print("[3] NO_PROVIDER — net.http with no HttpProvider:")
            r3 = kernel.submit(ActionRequest(action="net.http", target="https://example.com/api"))
            print_result(r3)
            print()

            # 4. INVALID — empty action and target
            print("[4] INVALID — empty action/target:")
            r4 = kernel.submit(ActionRequest(action="", target=""))
            print_result(r4)


if __name__ == "__main__":
    main()
