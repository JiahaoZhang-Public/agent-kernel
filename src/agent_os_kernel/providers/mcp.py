"""MCP (Model Context Protocol) provider for the Agent OS Kernel.

Handles mcp.call actions — routes tool calls to MCP servers via stdio transport.
Uses JSON-RPC 2.0 over stdin/stdout to communicate with MCP server processes.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from typing import Any

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.base import Provider

logger = logging.getLogger(__name__)


class McpClient:
    """Minimal MCP client using stdio transport (JSON-RPC 2.0).

    Spawns an MCP server process and communicates via stdin/stdout.
    Handles the initialize handshake and supports tools/call.
    """

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._env = env
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._initialized = False

    def connect(self) -> None:
        """Spawn the MCP server process and complete initialization handshake."""
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
        )
        self._do_initialize()

    def _do_initialize(self) -> None:
        """Perform the MCP initialize handshake."""
        result = self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-os-kernel", "version": "0.2.0"},
            },
        )
        if result is not None:
            # Send initialized notification (no response expected)
            self._send_notification("notifications/initialized", {})
            self._initialized = True

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call.
            arguments: Tool arguments.

        Returns:
            The tool result content.

        Raises:
            RuntimeError: If the server is not connected or returns an error.
        """
        if not self._initialized:
            raise RuntimeError("MCP client not initialized. Call connect() first.")

        result = self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments or {},
            },
        )

        if result is None:
            raise RuntimeError(f"No response from MCP server for tool: {tool_name}")

        # MCP tools/call returns {"content": [...], "isError": bool}
        if result.get("isError", False):
            content = result.get("content", [])
            error_text = content[0].get("text", "unknown error") if content else "unknown error"
            raise RuntimeError(f"MCP tool error: {error_text}")

        return result

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the MCP server."""
        if not self._initialized:
            raise RuntimeError("MCP client not initialized. Call connect() first.")

        result = self._send_request("tools/list", {})
        if result is None:
            return []
        tools: list[dict[str, Any]] = result.get("tools", [])
        return tools

    def close(self) -> None:
        """Terminate the MCP server process."""
        if self._process is not None:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                self._process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self._process.kill()
            finally:
                self._process = None
                self._initialized = False

    def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a JSON-RPC request and wait for response."""
        with self._lock:
            self._request_id += 1
            request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._write_message(message)
        return self._read_response(request_id)

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._write_message(message)

    def _write_message(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to the server's stdin."""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP server process not running")
        data = json.dumps(message) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        self._process.stdin.flush()

    def _read_response(self, request_id: int) -> Any:
        """Read a JSON-RPC response from the server's stdout."""
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("MCP server process not running")

        while True:
            line = self._process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed connection")

            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue

            try:
                response = json.loads(line_str)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from MCP server: %s", line_str[:200])
                continue

            # Skip notifications (no 'id' field)
            if "id" not in response:
                continue

            if response.get("id") != request_id:
                logger.warning(
                    "Unexpected response id: %s (expected %d)",
                    response.get("id"),
                    request_id,
                )
                continue

            if "error" in response:
                error = response["error"]
                raise RuntimeError(f"MCP error ({error.get('code', '?')}): {error.get('message', 'unknown')}")

            return response.get("result")


class McpProvider(Provider):
    """Provider for MCP tool calls.

    The target format is "server_name/tool_name", e.g. "scholar/search".
    MCP servers are configured at initialization with their command and env.

    Server config format:
        {
            "server_name": {
                "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path"],
                "env": {"KEY": "value"},  # optional
            }
        }
    """

    def __init__(self, servers: dict[str, Any] | None = None) -> None:
        """Initialize with MCP server configurations.

        Args:
            servers: Mapping of server names to connection configs.
                Each config must have a "command" key (list of strings).
                Optional "env" key for environment variables.
        """
        self._server_configs = servers or {}
        self._clients: dict[str, McpClient] = {}

    @property
    def actions(self) -> list[str]:
        return ["mcp.call"]

    def execute(self, request: ActionRequest) -> Any:
        target = request.target
        if "/" not in target:
            raise ValueError(f"MCP target must be 'server/tool' format: {target}")

        server_name, tool_name = target.split("/", 1)

        if server_name not in self._server_configs:
            raise ValueError(f"Unknown MCP server: {server_name}")

        client = self._get_or_create_client(server_name)
        arguments = request.params.get("arguments", request.params)
        # Remove non-argument keys
        arguments = {k: v for k, v in arguments.items() if k != "arguments"}

        return client.call_tool(tool_name, arguments)

    def _get_or_create_client(self, server_name: str) -> McpClient:
        """Get an existing client or create and connect a new one."""
        if server_name in self._clients:
            return self._clients[server_name]

        config = self._server_configs[server_name]
        command = config.get("command")
        if not command:
            raise ValueError(f"MCP server '{server_name}' config missing 'command'")

        env = config.get("env")
        client = McpClient(command=command, env=env)
        client.connect()
        self._clients[server_name] = client
        return client

    def close(self) -> None:
        """Close all MCP server connections."""
        for client in self._clients.values():
            client.close()
        self._clients.clear()
