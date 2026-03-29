#!/usr/bin/env python3
"""Audit log analysis: parse JSONL log and compute operational statistics.

Submits 20+ mixed actions through the kernel (reads, writes, denied
attempts, errors), then parses the resulting audit log to compute:
- Total actions count
- Count by status (OK, DENIED, ERROR)
- Average and max duration for OK actions
- List of denied targets
- Actions per second throughput

No LLM required.

Run:
    uv run python examples/08_advanced/audit_log_analysis.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.log import Log
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.process import ProcessProvider


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        (workspace / "output").mkdir()
        log_path = Path(tmp) / "kernel.log"

        # Seed workspace with files
        for i in range(5):
            (workspace / f"data_{i}.txt").write_text(f"Sample data file {i}\n" * 10)
        (workspace / "output" / "existing.txt").write_text("Existing output.\n")

        # Policy: read anywhere in workspace, write only to output/, allow echo
        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/output/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/output/**"),
                CapabilityRule(action="proc.exec", resource="echo"),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider(), ProcessProvider()],
            log_path=log_path,
        ) as kernel:
            start_time = time.monotonic()

            # ── OK actions: reads ────────────────────────────────────
            for i in range(5):
                kernel.submit(
                    ActionRequest(
                        action="fs.read",
                        target=str(workspace / f"data_{i}.txt"),
                    )
                )

            # ── OK actions: writes to output/ ────────────────────────
            for i in range(4):
                kernel.submit(
                    ActionRequest(
                        action="fs.write",
                        target=str(workspace / "output" / f"result_{i}.txt"),
                        params={"content": f"Analysis result {i}\n"},
                    )
                )

            # ── OK actions: process execution ────────────────────────
            for i in range(3):
                kernel.submit(
                    ActionRequest(
                        action="proc.exec",
                        target="echo",
                        params={"args": [f"batch-{i}"]},
                    )
                )

            # ── DENIED actions: write outside output/ ────────────────
            denied_targets = [
                str(workspace / "unauthorized.txt"),
                str(workspace / "data_0.txt"),  # write to read-only area
                str(Path(tmp) / "escape.txt"),  # outside workspace entirely
            ]
            for target in denied_targets:
                kernel.submit(
                    ActionRequest(
                        action="fs.write",
                        target=target,
                        params={"content": "should not appear"},
                    )
                )

            # ── DENIED actions: delete outside output/ ───────────────
            kernel.submit(
                ActionRequest(
                    action="fs.delete",
                    target=str(workspace / "data_0.txt"),
                )
            )

            # ── DENIED actions: disallowed action type ───────────────
            kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://example.com",
                    params={"method": "GET"},
                )
            )

            # ── DENIED actions: disallowed process ───────────────────
            kernel.submit(
                ActionRequest(
                    action="proc.exec",
                    target="rm",
                    params={"args": ["-rf", "/"]},
                )
            )

            # ── OK actions: delete from output/ ──────────────────────
            kernel.submit(
                ActionRequest(
                    action="fs.delete",
                    target=str(workspace / "output" / "existing.txt"),
                )
            )

            # ── More reads for volume ────────────────────────────────
            for i in range(3):
                kernel.submit(
                    ActionRequest(
                        action="fs.read",
                        target=str(workspace / f"data_{i}.txt"),
                    )
                )

            elapsed = time.monotonic() - start_time

        # ── Parse and analyze the audit log ──────────────────────────
        log = Log(log_path)
        records = log.read_all()

        print("=" * 60)
        print("AUDIT LOG ANALYSIS")
        print("=" * 60)
        print()

        # Total actions
        total = len(records)
        print(f"Total actions recorded: {total}")
        print()

        # Count by status
        status_counts: dict[str, int] = {}
        for rec in records:
            status_counts[rec.status] = status_counts.get(rec.status, 0) + 1

        print("Actions by status:")
        for status in sorted(status_counts):
            count = status_counts[status]
            bar = "#" * count
            print(f"  {status:<12} : {count:>3}  {bar}")
        print()

        # Duration statistics for OK actions
        ok_durations = [rec.duration_ms for rec in records if rec.status == "OK" and rec.duration_ms is not None]

        if ok_durations:
            avg_ms = sum(ok_durations) / len(ok_durations)
            max_ms = max(ok_durations)
            min_ms = min(ok_durations)
            print("Duration statistics (OK actions):")
            print(f"  Count   : {len(ok_durations)}")
            print(f"  Min     : {min_ms} ms")
            print(f"  Avg     : {avg_ms:.1f} ms")
            print(f"  Max     : {max_ms} ms")
        else:
            print("Duration statistics: no OK actions with duration data")
        print()

        # Denied targets
        denied_records = [rec for rec in records if rec.status == "DENIED"]
        print(f"Denied actions ({len(denied_records)}):")
        for rec in denied_records:
            target_display = rec.target
            if len(target_display) > 50:
                target_display = "..." + target_display[-47:]
            print(f"  {rec.action:<12} -> {target_display}")
        print()

        # Throughput
        if elapsed > 0:
            throughput = total / elapsed
            print("Throughput:")
            print(f"  Wall time      : {elapsed:.3f} s")
            print(f"  Actions/second : {throughput:.1f}")
        print()

        # Action type breakdown
        action_counts: dict[str, int] = {}
        for rec in records:
            action_counts[rec.action] = action_counts.get(rec.action, 0) + 1

        print("Actions by type:")
        for action in sorted(action_counts):
            count = action_counts[action]
            print(f"  {action:<12} : {count}")
        print()

        # Verify expectations
        assert total >= 20, f"Expected 20+ actions, got {total}"
        assert status_counts.get("OK", 0) >= 12, "Expected at least 12 OK actions"
        assert status_counts.get("DENIED", 0) >= 5, "Expected at least 5 DENIED actions"

        print("=" * 60)
        print(f"Success: {total} actions analyzed, all assertions passed.")


if __name__ == "__main__":
    main()
