#!/usr/bin/env python3
"""Convenience function example: run_agent_loop() one-liner.

Demonstrates the simplest way to run an agent — a single function call
that creates an AgentLoop internally and returns the result.

Run:
    uv run python examples/03_agent_loop/run_agent_loop_convenience.py
"""

from __future__ import annotations

import asyncio
import os

# Import shared helpers
import sys
import tempfile
from pathlib import Path

import litellm

from agent_os_kernel import Kernel, ToolDef, run_agent_loop
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

# ── Tool definition ─────────────────────────────────────────────────
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


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Seed workspace
        (workspace / "hello.txt").write_text("Hello from Agent OS Kernel! This file was read by an AI agent.")

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
            # One-liner: run_agent_loop() creates the AgentLoop internally
            result = await run_agent_loop(
                kernel=kernel,
                model=MODEL,
                prompt=f"Read the file at {workspace}/hello.txt and tell me what it says.",
                instructions="You are a helpful assistant. Use the read_file tool when asked to read files.",
                tools=[read_file],
            )

        print("=" * 60)
        print("Agent response:")
        print(result)
        print()
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    asyncio.run(main())
