#!/usr/bin/env python3
"""AgentLoop with ReversibleActionLayer: undo agent writes.

Plugs ReversibleActionLayer.submit into AgentLoop so that all agent
file writes are automatically snapshotted. After the agent produces
output, we demonstrate a manual rollback that restores the original
file content.

LLM required.

Run:
    uv run python examples/08_advanced/agent_with_reversible.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import litellm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import print_audit_log

from agent_os_kernel import AgentLoop, Kernel, ToolDef
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)

# ── LLM configuration ───────────────────────────────────────────────
API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

os.environ["OPENAI_API_KEY"] = API_KEY
if BASE_URL:
    litellm.api_base = BASE_URL

# ── Tool definitions (metadata-only) ────────────────────────────────

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
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        snapshot_dir = Path(tmp) / "snapshots"
        log_path = Path(tmp) / "kernel.log"

        # ── Step 1: Create workspace with existing report ────────────
        report_path = workspace / "report.txt"
        original_content = (
            "Q1 2026 Sales Report\n"
            "====================\n"
            "Total revenue: $125,000\n"
            "Units sold: 1,250\n"
            "Top product: Widget A\n"
        )
        report_path.write_text(original_content)

        print("Step 1: Workspace created with report.txt")
        print(f"  Path: {report_path}")
        print(f"  Content:\n{original_content}")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/**"),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            # ── Step 2: Set up reversible layer ──────────────────────
            layer = ReversibleActionLayer(
                kernel=kernel,
                strategies=[FsWriteSnapshotStrategy()],
                store=SnapshotStore(str(snapshot_dir)),
            )

            # KEY: pass layer.submit as the submit parameter
            loop = AgentLoop(
                kernel=kernel,
                model=MODEL,
                instructions=(
                    "You are a helpful assistant. When asked to analyze a report, "
                    "read it first, then write an analysis file with your findings."
                ),
                tools=[read_file, write_file],
                submit=layer.submit,  # All agent writes go through reversible layer
            )

            print("Step 2: AgentLoop created with reversible submit path")
            print("  submit = layer.submit (ReversibleActionLayer)")
            print()

            # ── Step 3: Agent writes analysis through reversible layer
            prompt = (
                f"Read the file at {report_path} and write a brief analysis "
                f"to {workspace}/analysis.txt summarizing key metrics and trends."
            )
            print("Step 3: Running agent with prompt...")
            print(f"  {prompt}\n")

            response = await loop.run(prompt)

            print("Agent response:")
            print(f"  {response[:200]}{'...' if len(response) > 200 else ''}")
            print()

            # ── Step 4: Show the report was written ──────────────────
            analysis_path = workspace / "analysis.txt"
            if analysis_path.exists():
                written_content = analysis_path.read_text()
                print("Step 4: analysis.txt was written by agent")
                print(f"  Content preview: {written_content[:150]}...")
                print()

                # ── Step 5: Demonstrate rollback ─────────────────────
                # Find the record_id from the snapshot store
                snapshots = list(Path(snapshot_dir).rglob("*.json")) if Path(snapshot_dir).exists() else []
                print(f"Step 5: Snapshot store contains {len(snapshots)} snapshot(s)")

                if snapshots:
                    # The layer tracks record_ids internally; we retrieve
                    # the last write's record_id from the audit log
                    from agent_os_kernel.log import Log

                    log = Log(log_path)
                    records = log.read_all()
                    write_records = [r for r in records if r.action == "fs.write" and r.status == "OK"]

                    if write_records:
                        # List snapshot files to find record_ids
                        snapshot_files = sorted(Path(snapshot_dir).glob("*.json"))
                        if snapshot_files:
                            record_id = snapshot_files[-1].stem  # filename without .json
                            print(f"  Rolling back record_id: {record_id}")

                            rollback_result = layer.rollback(record_id)
                            print(f"  Rollback status: {rollback_result.status}")

                            if analysis_path.exists():
                                restored = analysis_path.read_text()
                                print(f"  File after rollback: {restored[:100]}...")
                            else:
                                print("  File removed (was a new file, rollback deleted it)")
                            print()
                        else:
                            print("  No snapshots available for rollback.")
                            print()
                    else:
                        print("  No write records found in log.")
                        print()
            else:
                print("Step 4: Agent did not write analysis.txt (LLM may not have called the tool)")
                print()

        # ── Step 6: Print audit log ──────────────────────────────────
        print("=" * 60)
        print("Step 6: Audit log")
        print_audit_log(log_path)


if __name__ == "__main__":
    asyncio.run(main())
