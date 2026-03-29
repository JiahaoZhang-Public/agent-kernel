#!/usr/bin/env python3
"""Agent with filesystem, process, and HTTP tools -- all through one kernel.

Demonstrates an LLM-driven agent that can read/write files, execute
shell commands, and make HTTP requests, with every action going through
the kernel gate for policy enforcement and audit logging.

Run: OPENAI_API_KEY=sk-... uv run python examples/06_multi_provider/agent_with_all_providers.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import litellm

from agent_os_kernel import AgentLoop, Kernel, ToolDef
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.http import HttpProvider
from agent_os_kernel.providers.process import ProcessProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log

# ── LLM configuration ────────────────────────────────────────────────

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
if BASE_URL:
    litellm.api_base = BASE_URL


# ── Tool definitions (metadata only -- no execution logic) ────────────


def build_tools() -> list[ToolDef]:
    """Define the four tools the agent can use."""
    return [
        ToolDef(
            name="read_file",
            description="Read the contents of a file at the given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute file path to read"},
                },
                "required": ["path"],
            },
            action="fs.read",
            target_from="path",
        ),
        ToolDef(
            name="write_file",
            description="Write content to a file at the given path. Creates parent directories if needed.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute file path to write"},
                    "content": {"type": "string", "description": "Content to write to the file"},
                },
                "required": ["path", "content"],
            },
            action="fs.write",
            target_from="path",
        ),
        ToolDef(
            name="run_command",
            description="Execute a shell command and return its output.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Command arguments",
                    },
                },
                "required": ["command"],
            },
            action="proc.exec",
            target_from="command",
        ),
        ToolDef(
            name="http_request",
            description="Make an HTTP request to a URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to request"},
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, etc.)",
                        "default": "GET",
                    },
                },
                "required": ["url"],
            },
            action="net.http",
            target_from="url",
        ),
    ]


async def run() -> None:
    """Set up the kernel with all providers and run the agent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Policy: allow all four action types on appropriate resources
        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/**"),
                CapabilityRule(action="proc.exec", resource="echo"),
                CapabilityRule(action="proc.exec", resource="ls"),
                CapabilityRule(
                    action="net.http",
                    resource="https://httpbin.org/**",
                    constraint={"method": "GET"},
                ),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider(), ProcessProvider(), HttpProvider()],
            log_path=log_path,
        ) as kernel:
            agent = AgentLoop(
                kernel=kernel,
                model=MODEL,
                instructions=(
                    "You are a helpful assistant with access to filesystem, process, "
                    "and HTTP tools. All file paths must be absolute. "
                    f"The workspace directory is: {workspace}"
                ),
                tools=build_tools(),
                max_turns=10,
            )

            prompt = (
                f"Fetch a random UUID from https://httpbin.org/uuid, "
                f"then save it to {workspace}/output/uuid.txt, "
                f"then read the file back to confirm."
            )
            print(f"Prompt: {prompt}")
            print()

            response = await agent.run(prompt)
            print("Agent response:")
            print(response)
            print()

            # Verify the file was created
            uuid_file = workspace / "output" / "uuid.txt"
            if uuid_file.exists():
                content = uuid_file.read_text()
                print(f"Verification: {uuid_file} exists")
                print(f"  content: {content.strip()}")
            else:
                print(f"Verification: {uuid_file} was NOT created")
            print()

        # -- Audit log -----------------------------------------------------
        print("=" * 60)
        print("Audit log:")
        print_audit_log(log_path)


def main() -> None:
    """Entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
