#!/usr/bin/env python3
"""End-to-end agent demo with live LLM API via LiteLLM.

Demonstrates a real agent workflow:
1. Agent reads CSV data through kernel-native AgentLoop
2. Agent computes statistics and writes report
3. Agent rollbacks accidental overwrite via reversible layer
4. All actions authorized and logged by the kernel

Usage:
    OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.openai-proxy.org/v1 \
    OPENAI_MODEL=gpt-5.4-mini python scripts/e2e_agent_demo.py
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import litellm

from agent_os_kernel import ActionRequest, AgentLoop, Kernel, ToolDef
from agent_os_kernel.log import Log
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)

API_KEY = os.environ.get("OPENAI_API_KEY", "")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai-proxy.org/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")


async def run_demo(workspace: Path, log_path: str, snapshot_dir: str) -> None:
    print(f"Model: {MODEL}")
    print(f"Base URL: {BASE_URL}")
    print(f"Workspace: {workspace}")
    print()

    # Configure LiteLLM proxy
    if BASE_URL:
        litellm.api_base = BASE_URL

    # Write sample data
    (workspace / "output").mkdir(exist_ok=True)
    (workspace / "sales.csv").write_text(
        "month,product,revenue\n"
        "Jan,Widget A,12000\n"
        "Jan,Widget B,8500\n"
        "Feb,Widget A,14000\n"
        "Feb,Widget B,9200\n"
        "Mar,Widget A,13500\n"
        "Mar,Widget B,11000\n"
    )
    original_report = "Initial Q1 report: Pending analysis."
    (workspace / "output" / "report.txt").write_text(original_report)

    policy = Policy(
        capabilities=[
            CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
            CapabilityRule(action="fs.write", resource=f"{workspace}/output/**"),
        ]
    )

    kernel = Kernel(
        policy=policy,
        providers=[FilesystemProvider()],
        log_path=log_path,
    )

    store = SnapshotStore(snapshot_dir)
    layer = ReversibleActionLayer(
        kernel=kernel,
        strategies=[FsWriteSnapshotStrategy()],
        store=store,
    )

    # --- Tool definitions (pure data, no execution logic) ---
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

    # --- Step 1: Agent reads and analyzes data ---
    print("=" * 60)
    print("STEP 1: Agent reads sales data and writes analysis report")
    print("=" * 60)

    loop = AgentLoop(
        kernel=kernel,
        model=MODEL,
        instructions=(
            "You are a business analyst. "
            "Read CSV files, analyze sales data, and write concise reports. "
            "Always use the tools provided — do not invent data."
        ),
        tools=[read_file, write_file],
    )

    report_path = str(workspace / "output" / "report.txt")
    result = await loop.run(
        f"Read the sales data at {workspace}/sales.csv. "
        f"Calculate total revenue per product and overall, then write a 3-line summary "
        f"report to {report_path}.",
    )
    print(f"Agent response: {result}")
    print(f"\nReport file contents:\n{(workspace / 'output' / 'report.txt').read_text()}")

    # --- Step 2: Simulate accidental overwrite and rollback ---
    print("\n" + "=" * 60)
    print("STEP 2: Simulate accidental overwrite, then rollback")
    print("=" * 60)

    overwrite_result = layer.submit(
        ActionRequest(
            action="fs.write",
            target=report_path,
            params={"content": "ACCIDENTALLY OVERWRITTEN"},
        )
    )
    print(f"Accidental write: status={overwrite_result.status}, record_id={overwrite_result.record_id}")
    print(f"File now: {(workspace / 'output' / 'report.txt').read_text()!r}")

    if overwrite_result.record_id:
        rollback_result = layer.rollback(overwrite_result.record_id)
        print(f"Rollback: status={rollback_result.status}")
        print(f"File restored: {(workspace / 'output' / 'report.txt').read_text()!r}")

    # --- Step 3: Audit log summary ---
    print("\n" + "=" * 60)
    print("STEP 3: Audit log")
    print("=" * 60)
    kernel.close()

    records = Log(log_path).read_all()
    print(f"Total log entries: {len(records)}")
    for r in records:
        dur = f" ({r.duration_ms}ms)" if r.duration_ms is not None else ""
        err = f" <- {r.error}" if r.error else ""
        print(f"  [{r.status}] {r.action} -> {r.target[:60]}{dur}{err}")

    print(f"\nDemo complete. {len(records)} actions recorded.")


def main() -> None:
    if not API_KEY:
        print("ERROR: OPENAI_API_KEY environment variable not set.")
        return

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        log_path = str(Path(tmp) / "kernel.log")
        snapshot_dir = str(Path(tmp) / ".snapshots")

        asyncio.run(run_demo(workspace, log_path, snapshot_dir))


if __name__ == "__main__":
    main()
