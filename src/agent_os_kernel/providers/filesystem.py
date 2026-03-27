"""Filesystem provider for the Agent OS Kernel.

Handles fs.read, fs.write, and fs.delete actions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.base import Provider


class FilesystemProvider(Provider):
    """Provider for filesystem operations."""

    @property
    def actions(self) -> list[str]:
        return ["fs.read", "fs.write", "fs.delete"]

    def execute(self, request: ActionRequest) -> Any:
        if request.action == "fs.read":
            return self._read(request)
        elif request.action == "fs.write":
            return self._write(request)
        elif request.action == "fs.delete":
            return self._delete(request)
        else:
            raise ValueError(f"Unknown action: {request.action}")

    def _read(self, request: ActionRequest) -> str:
        path = Path(request.target)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {request.target}")
        return path.read_text()

    def _write(self, request: ActionRequest) -> dict[str, Any]:
        path = Path(request.target)
        content = request.params.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return {"bytes_written": len(content)}

    def _delete(self, request: ActionRequest) -> dict[str, bool]:
        path = Path(request.target)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {request.target}")
        path.unlink()
        return {"deleted": True}
