"""MCP (Model Context Protocol) provider for the Agent OS Kernel.

Handles mcp.call actions — routes tool calls to MCP servers.
This is a stub implementation; actual MCP integration requires
the MCP client library and server configuration.
"""

from __future__ import annotations

from typing import Any

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.base import Provider


class McpProvider(Provider):
    """Provider for MCP tool calls.

    The target format is "server_name/tool_name", e.g. "scholar/search".
    MCP server connections must be configured at initialization.
    """

    def __init__(self, servers: dict[str, Any] | None = None) -> None:
        """Initialize with MCP server configurations.

        Args:
            servers: Mapping of server names to connection configs.
                     Actual MCP client integration is deferred.
        """
        self._servers = servers or {}

    @property
    def actions(self) -> list[str]:
        return ["mcp.call"]

    def execute(self, request: ActionRequest) -> Any:
        target = request.target
        if "/" not in target:
            raise ValueError(f"MCP target must be 'server/tool' format: {target}")

        server_name, tool_name = target.split("/", 1)

        if server_name not in self._servers:
            raise ValueError(f"Unknown MCP server: {server_name}")

        # Stub: actual MCP call would go through the MCP client protocol
        raise NotImplementedError(f"MCP call to {server_name}/{tool_name} — actual MCP client integration pending")
