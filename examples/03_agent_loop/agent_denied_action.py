#!/usr/bin/env python3
"""Agent handles policy denial gracefully.

Demonstrates what happens when an agent tries to use a tool whose action
is denied by the kernel's policy. The agent receives a DENIED status and
should respond explaining that it cannot perform the requested operation.

Run:
    uv run python examples/03_agent_loop/agent_denied_action.py
"""

from __future__ import annotations

import asyncio
import os

# Import shared helpers
import sys
import tempfile
from pathlib import Path

import litellm

from agent_os_kernel import AgentLoop, Kernel, ToolDef
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log

# ── LLM configuration ───────────────────────────────────────────────
API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

# Configure LiteLLM
os.environ["OPENAI_API_KEY"] = API_KEY
if BASE_URL:
    litellm.api_base = BASE_URL

# ── Tool definitions ────────────────────────────────────────────────
# The agent is given both tools, but the policy only allows fs.read.
read_file = ToolDef(
    name="read_file",
    description="Read the contents of a file at the given path.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Full file path"}},
        "required": ["path"],
    },
    action="fs.read",
    target_from="path",
)

write_file = ToolDef(
    name="write_file",
    description="Write content to a file at the given path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full file path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
    action="fs.write",
    target_from="path",
)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        (workspace / "output").mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Policy only allows reading — NO write permission
        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            loop = AgentLoop(
                kernel=kernel,
                model=MODEL,
                instructions=(
                    "You are a helpful assistant. If a tool call is denied by "
                    "the system policy, explain to the user that you do not have "
                    "permission to perform that action."
                ),
                tools=[read_file, write_file],
            )

            prompt = f"Write 'hello world' to {workspace}/output/test.txt"
            print(f"Prompt: {prompt}\n")

            result = await loop.run(prompt)

        # ── Show results ────────────────────────────────────────────
        print("=" * 60)
        print("Agent response:")
        print(result)
        print()

        # Verify the file was NOT written
        test_path = workspace / "output" / "test.txt"
        print(f"File exists: {test_path.exists()}")
        if not test_path.exists():
            print("Confirmed: write was correctly denied by policy.")
        print()

        # Show the audit log with DENIED entry
        print("Audit log (note the DENIED entry for fs.write):")
        print_audit_log(log_path)


if __name__ == "__main__":
    asyncio.run(main())
