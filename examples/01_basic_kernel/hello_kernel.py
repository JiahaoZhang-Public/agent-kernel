#!/usr/bin/env python3
"""Minimal kernel usage: submit a single fs.read request.

Demonstrates the core submit() API — create a Kernel with one provider
and one policy rule, then read a file through the Gate.

Run:
    uv run python examples/01_basic_kernel/hello_kernel.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        (workspace / "hello.txt").write_text("Hello from Agent OS Kernel!")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as kernel:
            result = kernel.submit(ActionRequest(action="fs.read", target=str(workspace / "hello.txt")))

        print(f"status : {result.status}")
        print(f"data   : {result.data}")


if __name__ == "__main__":
    main()
