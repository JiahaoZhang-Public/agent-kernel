#!/usr/bin/env python3
"""Multi-tool agent: read, write, and delete files.

Demonstrates an agent with three tools that reads two source files,
combines them into a single output, and then deletes the originals.

Run:
    uv run python examples/03_agent_loop/multi_tool_agent.py
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

delete_file = ToolDef(
    name="delete_file",
    description="Delete a file at the given path.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Full file path"}},
        "required": ["path"],
    },
    action="fs.delete",
    target_from="path",
)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        (workspace / "output").mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Seed workspace with two source files
        (workspace / "part1.txt").write_text(
            "Chapter 1: The Agent OS Kernel provides a security boundary " "for all agent-world interactions.\n"
        )
        (workspace / "part2.txt").write_text(
            "Chapter 2: Every tool call passes through the Gate, which " "enforces policy before execution.\n"
        )

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/output/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/*.txt"),
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
                    "You are a file management assistant. Follow instructions "
                    "precisely for reading, combining, and deleting files."
                ),
                tools=[read_file, write_file, delete_file],
            )

            prompt = (
                f"Read {workspace}/part1.txt and {workspace}/part2.txt, "
                f"combine their contents into {workspace}/output/combined.txt, "
                f"then delete the original part1.txt and part2.txt files."
            )
            print(f"Prompt: {prompt}\n")

            result = await loop.run(prompt)

        # ── Verify results ──────────────────────────────────────────
        print("=" * 60)
        print("Agent response:")
        print(result)
        print()

        combined_path = workspace / "output" / "combined.txt"
        if combined_path.exists():
            print("Combined file (output/combined.txt):")
            print("-" * 40)
            print(combined_path.read_text())
        else:
            print("WARNING: Agent did not create combined.txt")

        part1_exists = (workspace / "part1.txt").exists()
        part2_exists = (workspace / "part2.txt").exists()
        print(f"part1.txt still exists: {part1_exists}")
        print(f"part2.txt still exists: {part2_exists}")
        if not part1_exists and not part2_exists:
            print("Originals successfully deleted.")
        print()

        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    asyncio.run(main())
