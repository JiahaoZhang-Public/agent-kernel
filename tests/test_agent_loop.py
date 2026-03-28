"""Tests for the kernel-native agent loop.

Tests cover:
- ToolDef metadata and target resolution
- AgentLoop tool-call-to-ActionRequest mapping
- Gate enforcement (all tool calls go through kernel.submit)
- Deny behavior (error returned to LLM, not exception)
- Max turns limit
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from agent_os_kernel.agent_loop import AgentLoop, ToolDef, run_agent_loop
from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest, ActionResult
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kernel(tmp_path):
    policy = Policy(
        capabilities=[
            CapabilityRule(action="fs.read", resource=f"{tmp_path}/workspace/**"),
            CapabilityRule(action="fs.write", resource=f"{tmp_path}/workspace/output/**"),
        ]
    )
    return Kernel(
        policy=policy,
        providers=[FilesystemProvider()],
        log_path=tmp_path / "kernel.log",
    )


def _make_tool_def():
    return ToolDef(
        name="read_file",
        description="Read the contents of a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        },
        action="fs.read",
        target_from="path",
    )


def _make_llm_response(finish_reason="stop", content="Done", tool_calls=None):
    """Build a mock LiteLLM response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    if tool_calls:
        message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        }

    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


def _make_tool_call(call_id="call_1", name="read_file", arguments='{"path": "/workspace/data.csv"}'):
    """Build a mock tool call object."""
    func = MagicMock()
    func.name = name
    func.arguments = arguments

    tc = MagicMock()
    tc.id = call_id
    tc.function = func
    return tc


# ---------------------------------------------------------------------------
# ToolDef Tests
# ---------------------------------------------------------------------------


class TestToolDef:
    def test_basic_creation(self):
        td = _make_tool_def()
        assert td.name == "read_file"
        assert td.action == "fs.read"
        assert td.target_from == "path"

    def test_target_from_string(self):
        td = ToolDef(
            name="write_file",
            description="Write a file",
            parameters={"type": "object", "properties": {}},
            action="fs.write",
            target_from="path",
        )
        assert isinstance(td.target_from, str)
        assert td.target_from == "path"

    def test_target_from_callable(self):
        td = ToolDef(
            name="call_server",
            description="Call a server",
            parameters={"type": "object", "properties": {}},
            action="mcp.call",
            target_from=lambda args: f"{args['server']}/{args['method']}",
        )
        assert callable(td.target_from)
        assert td.target_from({"server": "s1", "method": "search"}) == "s1/search"

    def test_default_target_from(self):
        td = ToolDef(
            name="my_tool",
            description="A tool",
            parameters={"type": "object", "properties": {}},
            action="custom",
        )
        assert td.target_from == "target"


# ---------------------------------------------------------------------------
# AgentLoop._tool_schemas Tests
# ---------------------------------------------------------------------------


class TestToolSchemas:
    def test_single_tool_schema(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        schemas = loop._tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "read_file"
        assert schemas[0]["function"]["description"] == "Read the contents of a file"
        assert schemas[0]["function"]["parameters"] == td.parameters
        kernel.close()

    def test_multiple_tools_schema(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        td1 = _make_tool_def()
        td2 = ToolDef(
            name="write_file",
            description="Write a file",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            action="fs.write",
            target_from="path",
        )
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td1, td2])

        schemas = loop._tool_schemas()
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert names == {"read_file", "write_file"}
        kernel.close()

    def test_empty_tools(self, tmp_path):
        kernel = _make_kernel(tmp_path)
        loop = AgentLoop(kernel=kernel, model="gpt-4o")

        schemas = loop._tool_schemas()
        assert schemas == []
        kernel.close()


# ---------------------------------------------------------------------------
# AgentLoop._execute_tool_call Tests
# ---------------------------------------------------------------------------


class TestExecuteToolCall:
    def test_allowed_action(self, tmp_path):
        """Allowed tool call → kernel submits and returns OK."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "data.csv").write_text("a,b\n1,2")

        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        tc = _make_tool_call(arguments=json.dumps({"path": str(ws / "data.csv")}))
        result_str = loop._execute_tool_call(tc)
        result = json.loads(result_str)

        assert result["status"] == "OK"
        assert result["data"] == "a,b\n1,2"
        assert result["error"] is None
        kernel.close()

    def test_denied_action(self, tmp_path):
        """Denied tool call → returns DENIED status as string, no exception."""
        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        tc = _make_tool_call(arguments=json.dumps({"path": "/etc/passwd"}))
        result_str = loop._execute_tool_call(tc)
        result = json.loads(result_str)

        assert result["status"] == "DENIED"
        assert result["error"] == "not permitted"
        kernel.close()

    def test_unknown_tool(self, tmp_path):
        """Unknown tool name → returns ERROR status."""
        kernel = _make_kernel(tmp_path)
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[])

        tc = _make_tool_call(name="nonexistent_tool")
        result_str = loop._execute_tool_call(tc)
        result = json.loads(result_str)

        assert result["status"] == "ERROR"
        assert "unknown tool" in result["error"]
        kernel.close()

    def test_target_from_callable(self, tmp_path):
        """Target resolved via callable."""
        kernel = _make_kernel(tmp_path)
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "file.txt").write_text("content")

        td = ToolDef(
            name="read_file",
            description="Read a file",
            parameters={
                "type": "object",
                "properties": {"filepath": {"type": "string"}},
            },
            action="fs.read",
            target_from=lambda args: args["filepath"],
        )
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        tc = _make_tool_call(arguments=json.dumps({"filepath": str(ws / "file.txt")}))
        result_str = loop._execute_tool_call(tc)
        result = json.loads(result_str)

        assert result["status"] == "OK"
        assert result["data"] == "content"
        kernel.close()

    def test_empty_arguments(self, tmp_path):
        """Tool call with empty arguments string."""
        kernel = _make_kernel(tmp_path)
        td = ToolDef(
            name="my_tool",
            description="A tool",
            parameters={"type": "object", "properties": {}},
            action="fs.read",
            target_from="path",
        )
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        tc = _make_tool_call(name="my_tool", arguments="")
        result_str = loop._execute_tool_call(tc)
        result = json.loads(result_str)

        # target falls back to tool name when key not in args
        assert result["status"] in ("DENIED", "ERROR")
        kernel.close()

    def test_submit_override(self, tmp_path):
        """Custom submit callable is used instead of kernel.submit."""
        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()

        custom_results = []

        def custom_submit(request: ActionRequest) -> ActionResult:
            custom_results.append(request)
            return ActionResult(status="OK", data="custom", error=None)

        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td], submit=custom_submit)

        tc = _make_tool_call(arguments=json.dumps({"path": "/any/path"}))
        result_str = loop._execute_tool_call(tc)
        result = json.loads(result_str)

        assert result["data"] == "custom"
        assert len(custom_results) == 1
        assert custom_results[0].action == "fs.read"
        kernel.close()


# ---------------------------------------------------------------------------
# AgentLoop.run Tests (mocked LLM)
# ---------------------------------------------------------------------------


class TestAgentLoopRun:
    def test_simple_text_response(self, tmp_path):
        """LLM returns text immediately → returned as result."""
        kernel = _make_kernel(tmp_path)
        loop = AgentLoop(kernel=kernel, model="gpt-4o")

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_make_llm_response(finish_reason="stop", content="Hello!")
            )
            result = asyncio.run(loop.run("Hi"))

        assert result == "Hello!"
        kernel.close()

    def test_tool_call_then_response(self, tmp_path):
        """LLM calls tool → kernel executes → LLM responds with text."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "data.csv").write_text("a,b\n1,2")

        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        tc = _make_tool_call(arguments=json.dumps({"path": str(ws / "data.csv")}))

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[
                    _make_llm_response(finish_reason="tool_calls", tool_calls=[tc]),
                    _make_llm_response(finish_reason="stop", content="The file has a,b and 1,2"),
                ]
            )
            result = asyncio.run(loop.run("Read the file"))

        assert "a,b" in result or "1,2" in result
        kernel.close()

    def test_max_turns_reached(self, tmp_path):
        """Loop respects max_turns limit."""
        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td], max_turns=2)

        tc = _make_tool_call(arguments=json.dumps({"path": "/workspace/x"}))

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            # Always return tool calls, never stop
            mock_litellm.acompletion = AsyncMock(
                return_value=_make_llm_response(finish_reason="tool_calls", tool_calls=[tc])
            )
            result = asyncio.run(loop.run("Loop forever"))

        assert result == "[max turns reached]"
        kernel.close()

    def test_multiple_tool_calls_in_one_turn(self, tmp_path):
        """Multiple tool calls in single LLM response all go through kernel."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "a.txt").write_text("aaa")
        (ws / "b.txt").write_text("bbb")

        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        tc1 = _make_tool_call(call_id="c1", arguments=json.dumps({"path": str(ws / "a.txt")}))
        tc2 = _make_tool_call(call_id="c2", arguments=json.dumps({"path": str(ws / "b.txt")}))

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[
                    _make_llm_response(finish_reason="tool_calls", tool_calls=[tc1, tc2]),
                    _make_llm_response(finish_reason="stop", content="Got aaa and bbb"),
                ]
            )
            result = asyncio.run(loop.run("Read both files"))

        assert "aaa" in result or "bbb" in result

        # Verify both reads were logged
        records = kernel.log.read_all()
        ok_reads = [r for r in records if r.action == "fs.read" and r.status == "OK"]
        assert len(ok_reads) == 2
        kernel.close()

    def test_denied_tool_call_continues_loop(self, tmp_path):
        """Denied tool call returns error to LLM; loop continues."""
        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()
        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td])

        # First: LLM tries to read /etc/passwd (denied)
        tc_denied = _make_tool_call(arguments=json.dumps({"path": "/etc/passwd"}))

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                side_effect=[
                    _make_llm_response(finish_reason="tool_calls", tool_calls=[tc_denied]),
                    _make_llm_response(finish_reason="stop", content="Access was denied"),
                ]
            )
            result = asyncio.run(loop.run("Read /etc/passwd"))

        # Loop continued and returned text
        assert "denied" in result.lower() or len(result) > 0

        # Verify DENIED was logged
        records = kernel.log.read_all()
        denied = [r for r in records if r.status == "DENIED"]
        assert len(denied) == 1
        kernel.close()

    def test_system_instructions_included(self, tmp_path):
        """System instructions are passed to the LLM."""
        kernel = _make_kernel(tmp_path)
        loop = AgentLoop(kernel=kernel, model="gpt-4o", instructions="You are helpful.")

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=_make_llm_response(finish_reason="stop", content="Ok"))
            asyncio.run(loop.run("Hi"))

        # Check that system message was included
        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."
        kernel.close()

    def test_no_instructions(self, tmp_path):
        """No system instructions → no system message."""
        kernel = _make_kernel(tmp_path)
        loop = AgentLoop(kernel=kernel, model="gpt-4o")

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=_make_llm_response(finish_reason="stop", content="Ok"))
            asyncio.run(loop.run("Hi"))

        call_args = mock_litellm.acompletion.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "user"
        kernel.close()


# ---------------------------------------------------------------------------
# run_agent_loop convenience function
# ---------------------------------------------------------------------------


class TestRunAgentLoop:
    def test_convenience_function(self, tmp_path):
        kernel = _make_kernel(tmp_path)

        with patch("agent_os_kernel.agent_loop.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_make_llm_response(finish_reason="stop", content="Result")
            )
            result = asyncio.run(run_agent_loop(kernel=kernel, model="gpt-4o", prompt="Hi"))

        assert result == "Result"
        kernel.close()


# ---------------------------------------------------------------------------
# Gate Enforcement Structural Tests
# ---------------------------------------------------------------------------


class TestGateEnforcement:
    def test_tooldef_has_no_methods(self):
        """ToolDef should be pure data — no callable methods beyond dataclass defaults."""
        import inspect

        # Get methods defined directly on ToolDef (not inherited from object/dataclass)
        custom_methods = [
            name for name, _ in inspect.getmembers(ToolDef, predicate=inspect.isfunction) if not name.startswith("_")
        ]
        assert custom_methods == [], f"ToolDef should have no custom methods, found: {custom_methods}"

    def test_execute_tool_call_only_uses_submit(self):
        """AgentLoop._execute_tool_call should only execute via kernel submit."""
        import inspect

        source = inspect.getsource(AgentLoop._execute_tool_call)
        # Must contain submit call
        assert "_submit(request)" in source or "_submit(" in source
        # Must NOT contain direct execution calls
        assert "subprocess" not in source
        assert "urllib" not in source
        assert "open(" not in source

    def test_every_tool_call_goes_through_kernel(self, tmp_path):
        """Verify kernel.submit is called for every tool call."""
        kernel = _make_kernel(tmp_path)
        td = _make_tool_def()

        submit_calls = []
        original_submit = kernel.submit

        def tracking_submit(request):
            submit_calls.append(request)
            return original_submit(request)

        loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[td], submit=tracking_submit)

        tc1 = _make_tool_call(call_id="c1", arguments=json.dumps({"path": "/workspace/a"}))
        tc2 = _make_tool_call(call_id="c2", arguments=json.dumps({"path": "/workspace/b"}))

        loop._execute_tool_call(tc1)
        loop._execute_tool_call(tc2)

        assert len(submit_calls) == 2
        assert submit_calls[0].action == "fs.read"
        assert submit_calls[1].action == "fs.read"
        kernel.close()
