"""Tests for the MCP provider implementation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.mcp import McpClient, McpProvider


class TestMcpClient:
    """Tests for the McpClient JSON-RPC communication."""

    def test_connect_requires_command(self):
        client = McpClient(command=["nonexistent_mcp_server_xyz"])
        with pytest.raises(FileNotFoundError):
            client.connect()

    def test_call_tool_before_connect_raises(self):
        client = McpClient(command=["echo"])
        with pytest.raises(RuntimeError, match="not initialized"):
            client.call_tool("test")

    def test_list_tools_before_connect_raises(self):
        client = McpClient(command=["echo"])
        with pytest.raises(RuntimeError, match="not initialized"):
            client.list_tools()

    def test_close_without_connect(self):
        """Close on unconnected client should not raise."""
        client = McpClient(command=["echo"])
        client.close()  # Should be a no-op

    def test_write_message_without_process_raises(self):
        client = McpClient(command=["echo"])
        with pytest.raises(RuntimeError, match="not running"):
            client._write_message({"test": True})

    def test_read_response_without_process_raises(self):
        client = McpClient(command=["echo"])
        with pytest.raises(RuntimeError, match="not running"):
            client._read_response(1)


class TestMcpClientWithMockProcess:
    """Test McpClient with mocked subprocess for protocol verification."""

    def _make_mock_process(self, responses: list[dict]):
        """Create a mock process that returns predefined responses."""
        proc = MagicMock()
        proc.stdin = MagicMock()

        # Build response lines
        lines = [json.dumps(r).encode("utf-8") + b"\n" for r in responses]
        proc.stdout = MagicMock()
        proc.stdout.readline = MagicMock(side_effect=lines)

        return proc

    @patch("agent_os_kernel.providers.mcp.subprocess.Popen")
    def test_initialize_handshake(self, mock_popen):
        """Verify the initialize/initialized handshake."""
        init_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test", "version": "1.0"},
            },
        }
        mock_popen.return_value = self._make_mock_process([init_response])

        client = McpClient(command=["test-server"])
        client.connect()

        assert client._initialized is True
        # Verify initialize request was sent
        calls = mock_popen.return_value.stdin.write.call_args_list
        assert len(calls) >= 1  # At least the initialize request

        first_call = json.loads(calls[0][0][0].decode("utf-8").strip())
        assert first_call["method"] == "initialize"
        assert first_call["params"]["protocolVersion"] == "2024-11-05"

        client.close()

    @patch("agent_os_kernel.providers.mcp.subprocess.Popen")
    def test_call_tool_sends_correct_request(self, mock_popen):
        """Verify tools/call sends correct JSON-RPC."""
        init_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
        tool_response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [{"type": "text", "text": "search results"}],
                "isError": False,
            },
        }
        mock_popen.return_value = self._make_mock_process([init_response, tool_response])

        client = McpClient(command=["test-server"])
        client.connect()
        result = client.call_tool("search", {"query": "test"})

        assert result["content"][0]["text"] == "search results"
        assert result["isError"] is False
        client.close()

    @patch("agent_os_kernel.providers.mcp.subprocess.Popen")
    def test_call_tool_error_response(self, mock_popen):
        """MCP tool returning isError=True should raise."""
        init_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
        error_response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [{"type": "text", "text": "tool failed"}],
                "isError": True,
            },
        }
        mock_popen.return_value = self._make_mock_process([init_response, error_response])

        client = McpClient(command=["test-server"])
        client.connect()

        with pytest.raises(RuntimeError, match="tool failed"):
            client.call_tool("broken_tool")

        client.close()

    @patch("agent_os_kernel.providers.mcp.subprocess.Popen")
    def test_jsonrpc_error_raises(self, mock_popen):
        """JSON-RPC level error should raise RuntimeError."""
        init_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
        error = {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32600, "message": "Invalid request"},
        }
        mock_popen.return_value = self._make_mock_process([init_response, error])

        client = McpClient(command=["test-server"])
        client.connect()

        with pytest.raises(RuntimeError, match="Invalid request"):
            client.call_tool("test")

        client.close()

    @patch("agent_os_kernel.providers.mcp.subprocess.Popen")
    def test_list_tools(self, mock_popen):
        """Verify tools/list returns tool definitions."""
        init_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
        list_response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {"name": "search", "description": "Search for papers"},
                    {"name": "cite", "description": "Get citation"},
                ],
            },
        }
        mock_popen.return_value = self._make_mock_process([init_response, list_response])

        client = McpClient(command=["test-server"])
        client.connect()
        tools = client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "search"
        client.close()


class TestMcpProvider:
    """Tests for the McpProvider."""

    def test_actions_list(self):
        provider = McpProvider()
        assert provider.actions == ["mcp.call"]

    def test_invalid_target_format(self):
        provider = McpProvider()
        with pytest.raises(ValueError, match="server/tool"):
            provider.execute(ActionRequest(action="mcp.call", target="no_slash"))

    def test_unknown_server(self):
        provider = McpProvider(servers={"known": {"command": ["echo"]}})
        with pytest.raises(ValueError, match="Unknown MCP server"):
            provider.execute(ActionRequest(action="mcp.call", target="unknown/tool"))

    def test_default_empty_servers(self):
        provider = McpProvider()
        with pytest.raises(ValueError, match="Unknown MCP server"):
            provider.execute(ActionRequest(action="mcp.call", target="any/tool"))

    def test_server_config_missing_command(self):
        provider = McpProvider(servers={"bad": {"env": {}}})
        with pytest.raises(ValueError, match="missing 'command'"):
            provider.execute(ActionRequest(action="mcp.call", target="bad/tool"))

    @patch("agent_os_kernel.providers.mcp.McpClient")
    def test_execute_calls_tool(self, mock_client_cls):
        """Verify execute routes to the correct MCP server and tool."""
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {
            "content": [{"type": "text", "text": "result"}],
            "isError": False,
        }
        mock_client_cls.return_value = mock_client

        provider = McpProvider(servers={"scholar": {"command": ["test-server"]}})
        result = provider.execute(
            ActionRequest(
                action="mcp.call",
                target="scholar/search",
                params={"arguments": {"query": "AI safety"}},
            )
        )

        mock_client.connect.assert_called_once()
        mock_client.call_tool.assert_called_once_with("search", {"query": "AI safety"})
        assert result["content"][0]["text"] == "result"

    @patch("agent_os_kernel.providers.mcp.McpClient")
    def test_reuses_client_for_same_server(self, mock_client_cls):
        """Second call to same server should reuse the client."""
        mock_client = MagicMock()
        mock_client.call_tool.return_value = {"content": [], "isError": False}
        mock_client_cls.return_value = mock_client

        provider = McpProvider(servers={"s1": {"command": ["cmd"]}})
        provider.execute(ActionRequest(action="mcp.call", target="s1/tool1", params={}))
        provider.execute(ActionRequest(action="mcp.call", target="s1/tool2", params={}))

        # Client should only be created once
        assert mock_client_cls.call_count == 1
        assert mock_client.connect.call_count == 1

    def test_close_cleans_up_clients(self):
        provider = McpProvider(servers={"s1": {"command": ["cmd"]}})
        mock_client = MagicMock()
        provider._clients["s1"] = mock_client

        provider.close()
        mock_client.close.assert_called_once()
        assert len(provider._clients) == 0
