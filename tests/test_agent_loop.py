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
