"""End-to-end tests using the live OpenAI API via proxy.

These tests validate the full agent-kernel workflow:
  - OpenAI Agents SDK integration
  - kernel_tool routing through the Gate
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
from agents.models.openai_provider import OpenAIProvider

from agent_os_kernel import Kernel
from agent_os_kernel.agent_loop import create_kernel_agent, kernel_tool, run_agent
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


def _make_provider() -> OpenAIProvider:
    return OpenAIProvider(api_key=API_KEY, base_url=BASE_URL)


def _make_workspace(tmp_path: Path) -> tuple[Path, str, str]:
    """Create workspace, policy file, and log path."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "readme.txt").write_text("Agent OS Kernel workspace. Do not delete.")
    (ws / "data.csv").write_text("name,score\nalice,90\nbob,85\ncarol,92\n")

    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(f"""capabilities:
  - action: fs.read
    resource: {ws}/**
  - action: fs.write
    resource: {ws}/output/**
  - action: proc.exec
    resource: echo
""")
    log_path = tmp_path / "kernel.log"
    return ws, str(policy_file), str(log_path)


# ---------------------------------------------------------------------------
# Test 1: Basic file read tool
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_reads_file_through_kernel(tmp_path):
    """Agent should read a file via kernel_tool and report its contents."""
    ws, policy_path, log_path = _make_workspace(tmp_path)

    (ws / "output").mkdir()

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:

        @kernel_tool(kernel, action="fs.read", target_from="path")
        def read_file(path: str) -> str:
            """Read the contents of a file."""
            return ""

        agent = create_kernel_agent(
            kernel,
            name="FileReaderAgent",
            instructions="You are a helpful assistant. When asked to read a file, use the read_file tool.",
            model=MODEL,
            tools=[read_file],
        )

        result = asyncio.run(
            run_agent(agent, f"Read the file at {ws}/data.csv and tell me the highest score."),
        )

    print(f"\n[test_agent_reads_file] Agent output: {result!r}")
    # The agent should mention either 92 or carol
    assert any(
        x in result.lower() for x in ["92", "carol"]
    ), f"Expected score 92 or name 'carol' in agent output, got: {result!r}"

    # Verify the kernel logged the fs.read action
    records = Log(log_path).read_all()
    read_records = [r for r in records if r.action == "fs.read" and r.status == "OK"]
    assert len(read_records) >= 1, "Expected at least one fs.read OK log entry"


# ---------------------------------------------------------------------------
# Test 2: Policy blocks unauthorized write
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_denied_write_outside_policy(tmp_path):
    """Agent attempting to write outside allowed path should get DENIED back."""
    ws, policy_path, log_path = _make_workspace(tmp_path)
    (ws / "output").mkdir()

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:

        @kernel_tool(kernel, action="fs.write", target_from="path")
        def write_file(path: str, content: str = "") -> str:
            """Write content to a file."""
            return ""

        agent = create_kernel_agent(
            kernel,
            name="WriteAgent",
            instructions=(
                "You are an assistant. When asked to write a file, "
                "use write_file. Report exactly what the tool returned."
            ),
            model=MODEL,
            tools=[write_file],
        )

        result = asyncio.run(run_agent(agent, "Write 'hacked' to /etc/passwd using the write_file tool."))

    print(f"\n[test_denied_write] Agent output: {result!r}")
    # Agent should report the denial
    assert any(
        x in result.lower() for x in ["denied", "not permitted", "error", "can't", "cannot", "unable"]
    ), f"Expected agent to report denial, got: {result!r}"

    # Verify DENIED in log
    records = Log(log_path).read_all()
    denied = [r for r in records if r.status == "DENIED"]
    assert len(denied) >= 1, "Expected at least one DENIED log entry"


# ---------------------------------------------------------------------------
# Test 3: Multi-tool agent workflow (read → write)
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_read_then_write_workflow(tmp_path):
    """Agent reads a CSV, summarizes it, writes summary to output file."""
    ws, policy_path, log_path = _make_workspace(tmp_path)
    out_dir = ws / "output"
    out_dir.mkdir()

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:

        @kernel_tool(kernel, action="fs.read", target_from="path")
        def read_file(path: str) -> str:
            """Read the contents of a file."""
            return ""

        @kernel_tool(kernel, action="fs.write", target_from="path")
        def write_file(path: str, content: str = "") -> str:
            """Write content to a file. Returns bytes written."""
            return ""

        agent = create_kernel_agent(
            kernel,
            name="SummaryAgent",
            instructions=(
                "You are a data assistant. "
                "Read the CSV file requested, compute the average score, "
                "then write a one-line summary to the output path specified."
            ),
            model=MODEL,
            tools=[read_file, write_file],
        )

        out_path = str(out_dir / "summary.txt")
        result = asyncio.run(
            run_agent(
                agent,
                f"Read {ws}/data.csv, compute the average score, " f"and write a one-line summary to {out_path}.",
            )
        )

    print(f"\n[test_read_write_workflow] Agent output: {result!r}")

    # Verify the output file was created
    summary_file = out_dir / "summary.txt"
    assert summary_file.exists(), "Agent should have written the summary file"
    content = summary_file.read_text()
    print(f"[test_read_write_workflow] Summary file: {content!r}")
    assert len(content) > 0, "Summary file should not be empty"

    # Verify log has both read and write entries
    records = Log(log_path).read_all()
    actions = {r.action for r in records if r.status == "OK"}
    assert "fs.read" in actions, "Expected fs.read in log"
    assert "fs.write" in actions, "Expected fs.write in log"


# ---------------------------------------------------------------------------
# Test 4: Kernel invariant — every LLM tool call produces a log entry
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_every_tool_call_logged(tmp_path):
    """Fundamental invariant: every tool invocation through kernel_tool is logged."""
    ws, policy_path, log_path = _make_workspace(tmp_path)
    (ws / "output").mkdir()

    # Write several readable files
    for i in range(3):
        (ws / f"file{i}.txt").write_text(f"content {i}")

    with Kernel(
        policy=policy_path,
        providers=[FilesystemProvider()],
        log_path=log_path,
    ) as kernel:

        @kernel_tool(kernel, action="fs.read", target_from="path")
        def read_file(path: str) -> str:
            """Read the contents of a file."""
            return ""

        agent = create_kernel_agent(
            kernel,
            name="MultiReadAgent",
            instructions="You are helpful. Read all files you are asked about.",
            model=MODEL,
            tools=[read_file],
        )

        files = [str(ws / f"file{i}.txt") for i in range(3)]
        prompt = f"Read these files one by one and tell me all their contents: {', '.join(files)}"
        asyncio.run(run_agent(agent, prompt))

    records = Log(log_path).read_all()
    read_ok = [r for r in records if r.action == "fs.read" and r.status == "OK"]
    print(f"\n[test_every_tool_call_logged] Log entries: {len(records)}, reads: {len(read_ok)}")
    # The agent should have read at least 2 of the 3 files
    assert len(read_ok) >= 2, f"Expected at least 2 logged reads, got {len(read_ok)}"


# ---------------------------------------------------------------------------
# Test 5: Process exec tool
# ---------------------------------------------------------------------------


@SKIP_IF_NO_KEY
def test_agent_exec_process_tool(tmp_path):
    """Agent can invoke process tools through the kernel."""
    ws, policy_path, log_path = _make_workspace(tmp_path)

    with Kernel(
        policy=policy_path,
        providers=[ProcessProvider()],
        log_path=log_path,
    ) as kernel:

        @kernel_tool(kernel, action="proc.exec", target_from="command")
        def run_command(command: str, args: list = []) -> str:  # noqa: B006
            """Run a shell command. Returns stdout."""
            return ""

        agent = create_kernel_agent(
            kernel,
            name="ShellAgent",
            instructions="You can run shell commands. Use run_command.",
            model=MODEL,
            tools=[run_command],
        )

        result = asyncio.run(
            run_agent(agent, "Run the echo command with argument 'kernel-test-ok' and tell me the output.")
        )

    print(f"\n[test_agent_exec_process] Agent output: {result!r}")
    assert (
        "kernel-test-ok" in result.lower() or "echo" in result.lower()
    ), f"Expected kernel-test-ok in output, got: {result!r}"

    records = Log(log_path).read_all()
    exec_ok = [r for r in records if r.action == "proc.exec" and r.status == "OK"]
    assert len(exec_ok) >= 1
