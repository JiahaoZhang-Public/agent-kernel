"""Tests for built-in providers (Filesystem, Process, Http, Mcp)."""

from __future__ import annotations

import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.http import HttpProvider
from agent_os_kernel.providers.mcp import McpProvider
from agent_os_kernel.providers.process import ProcessProvider

# ---------------------------------------------------------------------------
# FilesystemProvider
# ---------------------------------------------------------------------------


class TestFilesystemProvider:
    """Tests for the FilesystemProvider."""

    def test_actions_list(self):
        provider = FilesystemProvider()
        assert set(provider.actions) == {"fs.read", "fs.write", "fs.delete"}

    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        provider = FilesystemProvider()
        result = provider.execute(ActionRequest(action="fs.read", target=str(f)))
        assert result == "hello world"

    def test_read_nonexistent_file(self, tmp_path):
        provider = FilesystemProvider()
        with pytest.raises(FileNotFoundError):
            provider.execute(ActionRequest(action="fs.read", target=str(tmp_path / "nope.txt")))

    def test_write_creates_file(self, tmp_path):
        f = tmp_path / "out.txt"
        provider = FilesystemProvider()
        result = provider.execute(ActionRequest(action="fs.write", target=str(f), params={"content": "data"}))
        assert result == {"bytes_written": 4}
        assert f.read_text() == "data"

    def test_write_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "nested" / "dir" / "out.txt"
        provider = FilesystemProvider()
        provider.execute(ActionRequest(action="fs.write", target=str(f), params={"content": "x"}))
        assert f.read_text() == "x"

    def test_write_overwrites_existing_file(self, tmp_path):
        f = tmp_path / "out.txt"
        f.write_text("old")
        provider = FilesystemProvider()
        provider.execute(ActionRequest(action="fs.write", target=str(f), params={"content": "new"}))
        assert f.read_text() == "new"

    def test_write_default_empty_content(self, tmp_path):
        f = tmp_path / "empty.txt"
        provider = FilesystemProvider()
        result = provider.execute(ActionRequest(action="fs.write", target=str(f)))
        assert result == {"bytes_written": 0}
        assert f.read_text() == ""

    def test_delete_existing_file(self, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_text("bye")
        provider = FilesystemProvider()
        result = provider.execute(ActionRequest(action="fs.delete", target=str(f)))
        assert result == {"deleted": True}
        assert not f.exists()

    def test_delete_nonexistent_file(self, tmp_path):
        provider = FilesystemProvider()
        with pytest.raises(FileNotFoundError):
            provider.execute(ActionRequest(action="fs.delete", target=str(tmp_path / "nope.txt")))

    def test_unknown_action_raises(self, tmp_path):
        provider = FilesystemProvider()
        with pytest.raises(ValueError, match="Unknown action"):
            provider.execute(ActionRequest(action="fs.unknown", target=str(tmp_path / "x")))

    def test_read_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        provider = FilesystemProvider()
        result = provider.execute(ActionRequest(action="fs.read", target=str(f)))
        assert result == ""

    def test_write_and_read_roundtrip(self, tmp_path):
        f = tmp_path / "roundtrip.txt"
        provider = FilesystemProvider()
        content = "line1\nline2\nline3"
        provider.execute(ActionRequest(action="fs.write", target=str(f), params={"content": content}))
        result = provider.execute(ActionRequest(action="fs.read", target=str(f)))
        assert result == content


# ---------------------------------------------------------------------------
# ProcessProvider
# ---------------------------------------------------------------------------


class TestProcessProvider:
    """Tests for the ProcessProvider."""

    def test_actions_list(self):
        provider = ProcessProvider()
        assert provider.actions == ["proc.exec"]

    def test_exec_echo(self):
        provider = ProcessProvider()
        result = provider.execute(ActionRequest(action="proc.exec", target="echo", params={"args": ["hello"]}))
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_exec_with_no_args(self):
        provider = ProcessProvider()
        result = provider.execute(ActionRequest(action="proc.exec", target="echo", params={}))
        assert result["returncode"] == 0

    def test_exec_failing_command(self):
        provider = ProcessProvider()
        result = provider.execute(ActionRequest(action="proc.exec", target="false", params={}))
        assert result["returncode"] != 0

    def test_exec_with_cwd(self, tmp_path):
        provider = ProcessProvider()
        result = provider.execute(ActionRequest(action="proc.exec", target="pwd", params={"cwd": str(tmp_path)}))
        assert result["returncode"] == 0
        assert str(tmp_path) in result["stdout"]

    def test_exec_captures_stderr(self):
        provider = ProcessProvider()
        result = provider.execute(
            ActionRequest(
                action="proc.exec",
                target="sh",
                params={"args": ["-c", "echo err >&2"]},
            )
        )
        assert "err" in result["stderr"]

    def test_exec_git_version(self):
        """Verify git --version works (matches test_policy.yaml proc.exec rule)."""
        provider = ProcessProvider()
        result = provider.execute(ActionRequest(action="proc.exec", target="git", params={"args": ["--version"]}))
        assert result["returncode"] == 0
        assert "git version" in result["stdout"]

    def test_exec_nonexistent_command(self):
        provider = ProcessProvider()
        with pytest.raises(FileNotFoundError):
            provider.execute(ActionRequest(action="proc.exec", target="nonexistent_cmd_xyz", params={}))


# ---------------------------------------------------------------------------
# HttpProvider
# ---------------------------------------------------------------------------


class _TestHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for testing."""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # noqa: A002
        pass  # Suppress log output during tests


@pytest.fixture
def http_server():
    """Start a local HTTP server for testing."""
    server = HTTPServer(("127.0.0.1", 0), _TestHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestHttpProvider:
    """Tests for the HttpProvider."""

    def test_actions_list(self):
        provider = HttpProvider()
        assert provider.actions == ["net.http"]

    def test_get_request(self, http_server):
        provider = HttpProvider()
        result = provider.execute(
            ActionRequest(action="net.http", target=f"{http_server}/test", params={"method": "GET"})
        )
        assert result["status_code"] == 200
        assert result["body"] == "ok"

    def test_post_with_string_body(self, http_server):
        provider = HttpProvider()
        result = provider.execute(
            ActionRequest(
                action="net.http",
                target=f"{http_server}/test",
                params={"method": "POST", "body": "hello"},
            )
        )
        assert result["status_code"] == 200
        assert result["body"] == "hello"

    def test_post_with_dict_body(self, http_server):
        provider = HttpProvider()
        result = provider.execute(
            ActionRequest(
                action="net.http",
                target=f"{http_server}/test",
                params={"method": "POST", "body": {"key": "value"}},
            )
        )
        assert result["status_code"] == 200
        import json

        assert json.loads(result["body"]) == {"key": "value"}

    def test_default_method_is_get(self, http_server):
        provider = HttpProvider()
        result = provider.execute(ActionRequest(action="net.http", target=f"{http_server}/test"))
        assert result["status_code"] == 200

    def test_custom_headers(self, http_server):
        provider = HttpProvider()
        result = provider.execute(
            ActionRequest(
                action="net.http",
                target=f"{http_server}/test",
                params={"method": "GET", "headers": {"X-Custom": "val"}},
            )
        )
        assert result["status_code"] == 200

    def test_http_error_returns_status(self):
        """Connection to invalid port should raise."""
        provider = HttpProvider()
        with pytest.raises((OSError, urllib.error.URLError)):
            provider.execute(
                ActionRequest(
                    action="net.http",
                    target="http://127.0.0.1:1/nonexistent",
                    params={"timeout": 1},
                )
            )


# ---------------------------------------------------------------------------
# McpProvider — basic tests (comprehensive tests in test_mcp.py)
# ---------------------------------------------------------------------------


class TestMcpProviderBasic:
    """Basic tests for the McpProvider."""

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
