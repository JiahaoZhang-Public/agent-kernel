"""Real MCP server integration tests.

These tests spin up a real MCP server process (Python-based echo server)
and verify the McpProvider can connect, discover tools, and invoke them.

No external npm packages required — we use a self-contained Python MCP server
written using the `mcp` library that ships with openai-agents.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.mcp import McpClient, McpProvider

# ---------------------------------------------------------------------------
# Helper: self-contained Python MCP server script
# ---------------------------------------------------------------------------

MCP_SERVER_SCRIPT = textwrap.dedent("""
import sys
import json

# Minimal MCP server over stdio (JSON-RPC 2.0)
# Implements: initialize, tools/list, tools/call

def send(obj):
    line = json.dumps(obj)
    sys.stdout.write(line + "\\n")
    sys.stdout.flush()

def recv():
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())

TOOLS = [
    {
        "name": "echo",
        "description": "Echo back the input message",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
    {
        "name": "add",
        "description": "Add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
    },
    {
        "name": "fail_tool",
        "description": "A tool that always fails",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

while True:
    msg = recv()
    if msg is None:
        break

    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-mcp-server", "version": "1.0.0"},
            },
        })

    elif method == "notifications/initialized":
        pass  # notification, no response

    elif method == "tools/list":
        send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS},
        })

    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name == "echo":
            text = arguments.get("message", "")
            send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Echo: {text}"}],
                    "isError": False,
                },
            })
        elif tool_name == "add":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": str(a + b)}],
                    "isError": False,
                },
            })
        elif tool_name == "fail_tool":
            send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": "deliberate tool failure"}],
                    "isError": True,
                },
            })
        else:
            send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            })

    else:
        if msg_id is not None:
            send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            })
""")


@pytest.fixture
def mcp_server_script(tmp_path):
    """Write the MCP server script to a temp file and return its path."""
    script = tmp_path / "mcp_server.py"
    script.write_text(MCP_SERVER_SCRIPT)
    return str(script)


@pytest.fixture
def mcp_client(mcp_server_script):
    """Create and connect a McpClient to the test MCP server."""
    client = McpClient(command=[sys.executable, mcp_server_script])
    client.connect()
    yield client
    client.close()


# ---------------------------------------------------------------------------
# McpClient integration tests against real server process
# ---------------------------------------------------------------------------


class TestMcpClientRealServer:
    def test_connect_and_initialize(self, mcp_server_script):
        """Client should connect and complete initialization handshake."""
        client = McpClient(command=[sys.executable, mcp_server_script])
        client.connect()
        assert client._initialized is True
        client.close()

    def test_list_tools(self, mcp_client):
        """Should return the test server's tool list."""
        tools = mcp_client.list_tools()
        assert len(tools) == 3
        names = {t["name"] for t in tools}
        assert names == {"echo", "add", "fail_tool"}

    def test_echo_tool(self, mcp_client):
        """Echo tool should return prefixed message."""
        result = mcp_client.call_tool("echo", {"message": "hello kernel"})
        assert result["isError"] is False
        assert "Echo: hello kernel" in result["content"][0]["text"]

    def test_add_tool(self, mcp_client):
        """Add tool should return the sum of two numbers."""
        result = mcp_client.call_tool("add", {"a": 7, "b": 5})
        assert result["isError"] is False
        assert result["content"][0]["text"] == "12"

    def test_fail_tool_raises(self, mcp_client):
        """Tool returning isError=True should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="deliberate tool failure"):
            mcp_client.call_tool("fail_tool")

    def test_unknown_tool_raises(self, mcp_client):
        """Calling an unknown tool should raise RuntimeError (JSON-RPC error)."""
        with pytest.raises(RuntimeError, match="Unknown tool"):
            mcp_client.call_tool("does_not_exist")

    def test_multiple_calls_same_connection(self, mcp_client):
        """Multiple tool calls should work on the same connection."""
        for i in range(5):
            result = mcp_client.call_tool("echo", {"message": f"call-{i}"})
            assert f"Echo: call-{i}" in result["content"][0]["text"]

    def test_close_and_reconnect(self, mcp_server_script):
        """Closing and reopening a client should work."""
        client = McpClient(command=[sys.executable, mcp_server_script])
        client.connect()
        result = client.call_tool("echo", {"message": "first"})
        assert "first" in result["content"][0]["text"]
        client.close()

        # Reconnect
        client2 = McpClient(command=[sys.executable, mcp_server_script])
        client2.connect()
        result2 = client2.call_tool("echo", {"message": "second"})
        assert "second" in result2["content"][0]["text"]
        client2.close()


# ---------------------------------------------------------------------------
# McpProvider integration tests against real server process
# ---------------------------------------------------------------------------


class TestMcpProviderRealServer:
    def test_execute_echo_tool(self, mcp_server_script, tmp_path):
        """McpProvider should invoke echo tool and return result."""
        provider = McpProvider(
            servers={
                "test": {"command": [sys.executable, mcp_server_script]},
            }
        )

        result = provider.execute(
            ActionRequest(
                action="mcp.call",
                target="test/echo",
                params={"arguments": {"message": "via kernel"}},
            )
        )
        assert "Echo: via kernel" in result["content"][0]["text"]
        provider.close()

    def test_execute_add_tool(self, mcp_server_script):
        """McpProvider should invoke add tool and return sum."""
        provider = McpProvider(
            servers={
                "calc": {"command": [sys.executable, mcp_server_script]},
            }
        )

        result = provider.execute(
            ActionRequest(
                action="mcp.call",
                target="calc/add",
                params={"arguments": {"a": 10, "b": 32}},
            )
        )
        assert result["content"][0]["text"] == "42"
        provider.close()

    def test_provider_reuses_client(self, mcp_server_script):
        """McpProvider should reuse the same client for repeated calls."""
        provider = McpProvider(
            servers={
                "test": {"command": [sys.executable, mcp_server_script]},
            }
        )

        for i in range(3):
            result = provider.execute(
                ActionRequest(
                    action="mcp.call",
                    target="test/echo",
                    params={"arguments": {"message": f"msg-{i}"}},
                )
            )
            assert f"msg-{i}" in result["content"][0]["text"]

        # Only one client should have been created
        assert len(provider._clients) == 1
        provider.close()

    def test_fail_tool_propagates_error(self, mcp_server_script):
        """McpProvider should propagate tool errors as RuntimeError."""
        provider = McpProvider(
            servers={
                "test": {"command": [sys.executable, mcp_server_script]},
            }
        )

        with pytest.raises(RuntimeError, match="deliberate tool failure"):
            provider.execute(
                ActionRequest(
                    action="mcp.call",
                    target="test/fail_tool",
                    params={},
                )
            )
        provider.close()

    def test_provider_close_terminates_server(self, mcp_server_script):
        """close() should terminate all server processes."""
        provider = McpProvider(
            servers={
                "test": {"command": [sys.executable, mcp_server_script]},
            }
        )
        # Connect by making a call
        provider.execute(
            ActionRequest(
                action="mcp.call",
                target="test/echo",
                params={"arguments": {"message": "hi"}},
            )
        )
        assert len(provider._clients) == 1
        provider.close()
        assert len(provider._clients) == 0

    def test_mcp_provider_through_kernel(self, mcp_server_script, tmp_path):
        """McpProvider should work end-to-end through the Kernel Gate."""
        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.policy import CapabilityRule, Policy

        policy = Policy(
            capabilities=[
                CapabilityRule(action="mcp.call", resource="test/**"),
            ]
        )
        provider = McpProvider(
            servers={
                "test": {"command": [sys.executable, mcp_server_script]},
            }
        )
        log_path = tmp_path / "kernel.log"

        with Kernel(policy=policy, providers=[provider], log_path=log_path) as kernel:
            result = kernel.submit(
                ActionRequest(
                    action="mcp.call",
                    target="test/echo",
                    params={"arguments": {"message": "through gate"}},
                )
            )

        assert result.status == "OK"
        assert "Echo: through gate" in result.data["content"][0]["text"]

        # Log should show the mcp.call
        from agent_os_kernel.log import Log

        records = Log(log_path).read_all()
        mcp_records = [r for r in records if r.action == "mcp.call"]
        assert len(mcp_records) == 1
        assert mcp_records[0].status == "OK"

    def test_mcp_policy_blocks_unauthorized_server(self, mcp_server_script, tmp_path):
        """Policy should block mcp.call to unauthorized servers."""
        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.policy import CapabilityRule, Policy

        policy = Policy(
            capabilities=[
                CapabilityRule(action="mcp.call", resource="allowed/**"),  # not 'test'
            ]
        )
        provider = McpProvider(
            servers={
                "test": {"command": [sys.executable, mcp_server_script]},
            }
        )
        log_path = tmp_path / "kernel.log"

        with Kernel(policy=policy, providers=[provider], log_path=log_path) as kernel:
            result = kernel.submit(
                ActionRequest(
                    action="mcp.call",
                    target="test/echo",
                    params={"arguments": {"message": "blocked"}},
                )
            )

        assert result.status == "DENIED"
