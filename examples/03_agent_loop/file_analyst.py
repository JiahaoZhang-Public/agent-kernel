#!/usr/bin/env python3
"""File analyst agent: reads CSV data and writes an analysis report.

Demonstrates an agent with two tools (read_file, write_file) that acts
as a business analyst — reading a sales CSV, analysing the data, and
writing a summary report to disk.

Run:
    uv run python examples/03_agent_loop/file_analyst.py
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

# ── Sample CSV data ─────────────────────────────────────────────────
SALES_CSV = """\
month,product,revenue
2026-01,Widget A,12500.00
2026-01,Widget B,8300.00
2026-02,Widget A,14200.00
2026-02,Widget B,9100.00
2026-03,Widget A,11800.00
2026-03,Widget B,10500.00
"""


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        (workspace / "output").mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Write sample sales data
        (workspace / "sales.csv").write_text(SALES_CSV)

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/output/**"),
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
                    "You are a business analyst. Read CSV files, analyze the data, " "and write clear summary reports."
                ),
                tools=[read_file, write_file],
            )

            prompt = (
                f"Read the file at {workspace}/sales.csv, calculate total revenue "
                f"per product and overall total revenue, then write a summary "
                f"report to {workspace}/output/report.txt"
            )
            print(f"Prompt: {prompt}\n")

            result = await loop.run(prompt)

        # ── Show results ────────────────────────────────────────────
        print("=" * 60)
        print("Agent response:")
        print(result)
        print()

        report_path = workspace / "output" / "report.txt"
        if report_path.exists():
            print("Written report (output/report.txt):")
            print("-" * 40)
            print(report_path.read_text())
        else:
            print("WARNING: Agent did not write report.txt")

        print()
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    asyncio.run(main())
