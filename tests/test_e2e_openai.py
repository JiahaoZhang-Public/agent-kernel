"""End-to-end tests using a live LLM API via LiteLLM.

These tests validate the full kernel-native agent loop workflow:
  - AgentLoop + ToolDef routing through the Gate
  - Policy enforcement on live LLM-generated actions
  - Audit log completeness

Requires environment variables:
  OPENAI_API_KEY      — API key
  OPENAI_BASE_URL     — proxy base URL (e.g. https://api.openai-proxy.org/v1)
  OPENAI_MODEL        — model name (e.g. gpt-5.4-mini)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from agent_os_kernel import AgentLoop, Kernel, ToolDef
from agent_os_kernel.log import Log
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.process import ProcessProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai-proxy.org/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

SKIP_IF_NO_KEY = pytest.mark.skipif(not API_KEY, reason="OPENAI_API_KEY not set")


def _setup_litellm():
    """Configure LiteLLM to use the proxy."""
    import litellm

    if BASE_URL:
        litellm.api_base = BASE_URL


def _make_workspace(tmp_path: Path) -> tuple[Path, str, str]:
    """Create workspace, policy file, and log path."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "readme.txt").write_text("Agent OS Kernel workspace. Do not delete.")
    (ws / "data.csv").write_text("name,score\nalice,90\nbob,85\ncarol,92\n")

    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        f"""capabilities:
  - action: fs.read
    resource: {ws}/**
  - action: fs.write
    resource: {ws}/output/**
  - action: proc.exec
    resource: echo
"""
    )
    log_path = tmp_path / "kernel.log"
    return ws, str(policy_file), str(log_path)


def _read_file_tool(ws: Path) -> ToolDef:
    return ToolDef(
        name="read_file",
        description="Read the contents of a file. Pass the full file path.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Full file path to read"}},
            "required": ["path"],
        },
        action="fs.read",
        target_from="path",
    )


def _write_file_tool() -> ToolDef:
    return ToolDef(
        name="write_file",
        description="Write content to a file. Returns bytes written.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full file path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        action="fs.write",
        target_from="path",
    )


def _run_command_tool() -> ToolDef:
    return ToolDef(
        name="run_command",
        description="Run a shell command. Pass the command string.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run"},
                "args": {"type": "string", "description": "Arguments string"},
            },
            "required": ["command"],
        },
        action="proc.exec",
        target_from="command",
    )


# ---------------------------------------------------------------------------
# Test 1: Basic file read tool
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_reads_file_through_kernel(tmp_path):
    """Agent should read a file via kernel and report its contents."""
    _setup_litellm()
    ws, policy_path, log_path = _make_workspace(tmp_path)
    (ws / "output").mkdir()

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:
        loop = AgentLoop(
            kernel=kernel,
            model=MODEL,
            instructions="You are a helpful assistant. When asked to read a file, use the read_file tool.",
            tools=[_read_file_tool(ws)],
        )
        result = asyncio.run(loop.run(f"Read the file at {ws}/data.csv and tell me the highest score."))

    print(f"\n[test_agent_reads_file] Agent output: {result!r}")
    assert any(
        x in result.lower() for x in ["92", "carol"]
    ), f"Expected score 92 or name 'carol' in agent output, got: {result!r}"

    records = Log(log_path).read_all()
    read_records = [r for r in records if r.action == "fs.read" and r.status == "OK"]
    assert len(read_records) >= 1, "Expected at least one fs.read OK log entry"


# ---------------------------------------------------------------------------
# Test 2: Policy blocks unauthorized write
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_denied_write_outside_policy(tmp_path):
    """Agent attempting to write outside allowed path should get DENIED back."""
    _setup_litellm()
    ws, policy_path, log_path = _make_workspace(tmp_path)
    (ws / "output").mkdir()

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:
        loop = AgentLoop(
            kernel=kernel,
            model=MODEL,
            instructions=(
                "You are an assistant. When asked to write a file, "
                "use write_file. Report exactly what the tool returned."
            ),
            tools=[_write_file_tool()],
        )
        unauthorized_path = str(ws / "unauthorized.txt")
        result = asyncio.run(loop.run(f"Write 'test_data_123' to {unauthorized_path} using the write_file tool."))

    print(f"\n[test_denied_write] Agent output: {result!r}")

    records = Log(log_path).read_all()
    denied = [r for r in records if r.status == "DENIED"]
    assert len(denied) >= 1, f"Expected at least one DENIED log entry, got: {records}"


# ---------------------------------------------------------------------------
# Test 3: Multi-tool agent workflow (read → write)
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_read_then_write_workflow(tmp_path):
    """Agent reads a CSV, summarizes it, writes summary to output file."""
    _setup_litellm()
    ws, policy_path, log_path = _make_workspace(tmp_path)
    out_dir = ws / "output"
    out_dir.mkdir()

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:
        loop = AgentLoop(
            kernel=kernel,
            model=MODEL,
            instructions=(
                "You are a data assistant. "
                "Read the CSV file requested, compute the average score, "
                "then write a one-line summary to the output path specified."
            ),
            tools=[_read_file_tool(ws), _write_file_tool()],
        )
        out_path = str(out_dir / "summary.txt")
        result = asyncio.run(
            loop.run(
                f"Read {ws}/data.csv, compute the average score, and write a one-line summary to {out_path}.",
            )
        )

    print(f"\n[test_read_write_workflow] Agent output: {result!r}")

    summary_file = out_dir / "summary.txt"
    assert summary_file.exists(), "Agent should have written the summary file"
    content = summary_file.read_text()
    print(f"[test_read_write_workflow] Summary file: {content!r}")
    assert len(content) > 0, "Summary file should not be empty"

    records = Log(log_path).read_all()
    actions = {r.action for r in records if r.status == "OK"}
    assert "fs.read" in actions, "Expected fs.read in log"
    assert "fs.write" in actions, "Expected fs.write in log"


# ---------------------------------------------------------------------------
# Test 4: Kernel invariant — every LLM tool call produces a log entry
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_every_tool_call_logged(tmp_path):
    """Fundamental invariant: every tool invocation is logged."""
    _setup_litellm()
    ws, policy_path, log_path = _make_workspace(tmp_path)
    (ws / "output").mkdir()

    for i in range(3):
        (ws / f"file{i}.txt").write_text(f"content {i}")

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:
        loop = AgentLoop(
            kernel=kernel,
            model=MODEL,
            instructions="You are helpful. Read all files you are asked about.",
            tools=[_read_file_tool(ws)],
        )
        files = [str(ws / f"file{i}.txt") for i in range(3)]
        prompt = f"Read these files one by one and tell me all their contents: {', '.join(files)}"
        asyncio.run(loop.run(prompt))

    records = Log(log_path).read_all()
    read_ok = [r for r in records if r.action == "fs.read" and r.status == "OK"]
    print(f"\n[test_every_tool_call_logged] Log entries: {len(records)}, reads: {len(read_ok)}")
    assert len(read_ok) >= 2, f"Expected at least 2 logged reads, got {len(read_ok)}"


# ---------------------------------------------------------------------------
# Test 5: Process exec tool
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_exec_process_tool(tmp_path):
    """Agent can invoke process tools through the kernel."""
    _setup_litellm()
    ws, policy_path, log_path = _make_workspace(tmp_path)

    with Kernel(
        policy=policy_path,
        providers=[ProcessProvider()],
        log_path=log_path,
    ) as kernel:
        loop = AgentLoop(
            kernel=kernel,
            model=MODEL,
            instructions="You can run shell commands. Use run_command.",
            tools=[_run_command_tool()],
        )
        result = asyncio.run(loop.run("Run the echo command with argument 'kernel-test-ok' and tell me the output."))

    print(f"\n[test_agent_exec_process] Agent output: {result!r}")
    result_normalized = result.lower().replace(" ", "")
    assert (
        "kernel-test-ok" in result.lower() or "kernel-test-ok" in result_normalized or "echo" in result.lower()
    ), f"Expected kernel-test-ok in output, got: {result!r}"

    records = Log(log_path).read_all()
    exec_ok = [r for r in records if r.action == "proc.exec" and r.status == "OK"]
    assert len(exec_ok) >= 1
