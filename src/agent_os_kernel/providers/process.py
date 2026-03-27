"""Process provider for the Agent OS Kernel.

Handles proc.exec actions — runs shell commands.
"""

from __future__ import annotations

import subprocess
from typing import Any

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.base import Provider

DEFAULT_TIMEOUT = 30


class ProcessProvider(Provider):
    """Provider for process execution."""

    @property
    def actions(self) -> list[str]:
        return ["proc.exec"]

    def execute(self, request: ActionRequest) -> Any:
        command = request.target
        args = request.params.get("args", [])
        timeout = request.params.get("timeout", DEFAULT_TIMEOUT)
        cwd = request.params.get("cwd")

        cmd = [command, *args] if args else [command]

        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
