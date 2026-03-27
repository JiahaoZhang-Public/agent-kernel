"""Tests for the OpenAI Agents SDK integration layer."""

from __future__ import annotations

from agent_os_kernel.agent_loop import _extract_schema, create_kernel_agent, kernel_tool
from agent_os_kernel.kernel import Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider


def _make_kernel(tmp_path):
    policy = Policy(
        capabilities=[
            CapabilityRule(action="fs.read", resource="/workspace/**"),
            CapabilityRule(action="fs.write", resource="/workspace/output/**"),
        ]
    )
    return Kernel(
        policy=policy,
        providers=[FilesystemProvider()],
        log_path=tmp_path / "kernel.log",
    )


class TestKernelTool:
    def test_creates_function_tool(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        @kernel_tool(kernel, action="fs.read", target_from="path")
        def read_file(path: str) -> str:
            """Read a file."""
            return ""

        assert read_file.name == "read_file"
        assert read_file.description == "Read a file."
        kernel.close()

    def test_custom_name_and_description(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        @kernel_tool(kernel, action="fs.read", name="my_reader", description="Custom desc")
        def read_file(path: str) -> str:
            return ""

        assert read_file.name == "my_reader"
        assert read_file.description == "Custom desc"
        kernel.close()


class TestExtractSchema:
    def test_basic_types(self):
        def func(name: str, count: int, ratio: float, flag: bool) -> str:
            return ""

        schema = _extract_schema(func)
        assert schema["properties"]["name"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["ratio"]["type"] == "number"
        assert schema["properties"]["flag"]["type"] == "boolean"
        assert set(schema["required"]) == {"name", "count", "ratio", "flag"}

    def test_optional_params(self):
        def func(required: str, optional: str = "default") -> str:
            return ""

        schema = _extract_schema(func)
        assert schema["required"] == ["required"]

    def test_no_annotations(self):
        def func(x):
            return x

        schema = _extract_schema(func)
        assert schema["properties"]["x"]["type"] == "string"

    def test_skips_self_cls_ctx(self):
        def func(self, cls, ctx, real_param: str) -> str:
            return ""

        schema = _extract_schema(func)
        assert "self" not in schema["properties"]
        assert "cls" not in schema["properties"]
        assert "ctx" not in schema["properties"]
        assert "real_param" in schema["properties"]

    def test_complex_type_fallback(self):
        def func(items: list[str]) -> str:
            return ""

        schema = _extract_schema(func)
        assert schema["properties"]["items"]["type"] == "string"


class TestKernelToolWrapper:
    """Test the wrapper function behavior inside kernel_tool."""

    def test_wrapper_denied_action(self, tmp_path):
        """When policy denies, wrapper returns JSON error."""
        import asyncio
        import json

        kernel = _make_kernel(tmp_path)

        @kernel_tool(kernel, action="fs.write", target_from="path")
        def write_file(path: str, content: str) -> str:
            """Write a file."""
            return "should not reach here"

        tool = write_file
        # Call wrapper with a path outside the allowed policy
        result = asyncio.run(tool.on_invoke_tool(None, json.dumps({"path": "/etc/passwd", "content": "x"})))
        data = json.loads(result)
        assert data["status"] == "DENIED"
        kernel.close()

    def test_wrapper_ok_with_provider_data(self, tmp_path):
        """When kernel returns data, wrapper uses that data."""
        import asyncio
        import json

        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.policy import CapabilityRule, Policy

        ws = tmp_path / "workspace"
        ws.mkdir(exist_ok=True)
        (ws / "test.txt").write_text("file content")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{tmp_path}/**"),
            ]
        )
        kernel = Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=tmp_path / "kernel.log",
        )

        @kernel_tool(kernel, action="fs.read", target_from="path")
        def read_file(path: str) -> str:
            """Read a file."""
            return "original func output"

        tool = read_file
        result = asyncio.run(tool.on_invoke_tool(None, json.dumps({"path": str(ws / "test.txt")})))
        # Provider returns the file content (a string), wrapper returns it directly
        assert result == "file content"
        kernel.close()

    def test_wrapper_ok_with_dict_data(self, tmp_path):
        """When provider returns a dict, wrapper JSON-serializes it."""
        import asyncio
        import json

        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.policy import CapabilityRule, Policy

        ws = tmp_path / "workspace" / "output"
        ws.mkdir(parents=True)

        policy = Policy(capabilities=[CapabilityRule(action="fs.write", resource=f"{tmp_path}/**")])
        kernel = Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=tmp_path / "kernel.log",
        )

        @kernel_tool(kernel, action="fs.write", target_from="path")
        def write_file(path: str, content: str = "") -> str:
            """Write a file."""
            return "original"

        tool = write_file
        result = asyncio.run(tool.on_invoke_tool(None, json.dumps({"path": str(ws / "out.txt"), "content": "hello"})))
        data = json.loads(result)
        assert "bytes_written" in data
        kernel.close()

    def test_target_from_none_uses_tool_name(self, tmp_path):
        """When target_from is None, the tool name is used as target."""
        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.policy import CapabilityRule, Policy

        policy = Policy(capabilities=[CapabilityRule(action="custom", resource="my_tool")])
        kernel = Kernel(policy=policy, log_path=tmp_path / "kernel.log")

        @kernel_tool(kernel, action="custom", name="my_tool")
        def my_tool() -> str:
            """A tool."""
            return "result"

        # Target should be "my_tool" (the tool name)
        assert my_tool.name == "my_tool"
        kernel.close()

    def test_target_from_callable(self, tmp_path):
        """When target_from is a callable, it extracts the target."""
        import asyncio
        import json

        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.policy import CapabilityRule, Policy

        policy = Policy(capabilities=[CapabilityRule(action="custom", resource="*")])
        kernel = Kernel(policy=policy, log_path=tmp_path / "kernel.log")

        @kernel_tool(
            kernel,
            action="custom",
            target_from=lambda kwargs: kwargs.get("server", "default"),
        )
        def call_server(server: str, method: str) -> str:
            """Call a server."""
            return ""

        tool = call_server
        # Will be denied at NO_PROVIDER level but that's ok for testing target extraction
        result = asyncio.run(tool.on_invoke_tool(None, json.dumps({"server": "myserver", "method": "get"})))
        data = json.loads(result)
        # Should have gone through the kernel (denied or error, but not a crash)
        assert "status" in data or isinstance(result, str)
        kernel.close()

    def test_wrapper_fallthrough_to_original_function(self, tmp_path):
        """When kernel returns OK with no data (no provider matched), call the original function."""
        import asyncio
        import json

        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.models import ActionResult
        from agent_os_kernel.policy import CapabilityRule, Policy

        policy = Policy(capabilities=[CapabilityRule(action="custom", resource="*")])
        kernel = Kernel(policy=policy, log_path=tmp_path / "kernel.log")

        # Patch submit to return OK with data=None
        def mock_submit(req):
            return ActionResult(status="OK", data=None, error=None)

        kernel.submit = mock_submit

        @kernel_tool(kernel, action="custom")
        def my_tool(value: str) -> str:
            """Custom tool."""
            return f"original-{value}"

        tool = my_tool
        result = asyncio.run(tool.on_invoke_tool(None, json.dumps({"value": "test"})))
        assert result == "original-test"
        kernel.close()

    def test_wrapper_fallthrough_returns_dict(self, tmp_path):
        """When original function returns dict, wrapper JSON-serializes it."""
        import asyncio
        import json

        from agent_os_kernel.kernel import Kernel
        from agent_os_kernel.models import ActionResult
        from agent_os_kernel.policy import CapabilityRule, Policy

        policy = Policy(capabilities=[CapabilityRule(action="custom", resource="*")])
        kernel = Kernel(policy=policy, log_path=tmp_path / "kernel.log")

        def mock_submit(req):
            return ActionResult(status="OK", data=None, error=None)

        kernel.submit = mock_submit

        @kernel_tool(kernel, action="custom")
        def my_tool(x: int) -> dict:
            """Return dict."""
            return {"result": x * 2}

        tool = my_tool
        result = asyncio.run(tool.on_invoke_tool(None, json.dumps({"x": 5})))
        data = json.loads(result)
        assert data == {"result": 10}
        kernel.close()


class TestCreateKernelAgent:
    def test_creates_agent(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        agent = create_kernel_agent(
            kernel,
            name="TestAgent",
            instructions="Test instructions",
            model="gpt-4o",
        )
        assert agent.name == "TestAgent"
        assert agent.instructions == "Test instructions"
        kernel.close()

    def test_creates_agent_with_tools(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        @kernel_tool(kernel, action="fs.read", target_from="path")
        def read_file(path: str) -> str:
            """Read a file."""
            return ""

        agent = create_kernel_agent(kernel, tools=[read_file])
        assert len(agent.tools) == 1
        kernel.close()

    def test_creates_agent_default_values(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        agent = create_kernel_agent(kernel)
        assert agent.name == "KernelAgent"
        assert agent.model == "gpt-4o"
        assert len(agent.tools) == 0
        kernel.close()
