"""Shared helpers for Agent OS Kernel examples.

Provides workspace setup, LLM configuration, and result formatting
utilities used across all example scripts.
"""

from __future__ import annotations

import os
from pathlib import Path

import litellm

from agent_os_kernel.log import Log
from agent_os_kernel.models import ActionResult

# ── LLM defaults ──────────────────────────────────────────────────────

DEFAULT_API_KEY = ""
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.4-mini"

# ── Sample data ───────────────────────────────────────────────────────

SAMPLE_DATA_TXT = """\
Agent OS Kernel — sample data file.
This file is used by the example scripts to demonstrate fs.read.
"""

SAMPLE_SALES_CSV = """\
date,product,quantity,revenue
2026-01-15,Widget A,120,2400.00
2026-01-16,Widget B,85,1700.00
2026-01-17,Widget A,200,4000.00
2026-01-18,Widget C,50,1500.00
"""

POLICY_TEMPLATE = """\
capabilities:
  - action: fs.read
    resource: "{workspace}/**"
  - action: fs.write
    resource: "{workspace}/output/**"
  - action: fs.delete
    resource: "{workspace}/output/**"
"""


def setup_workspace(base_dir: str | Path) -> tuple[Path, Path, Path]:
    """Create a workspace with sample files, a policy, and a log path.

    Args:
        base_dir: Root directory (typically a tempdir) to create workspace in.

    Returns:
        (workspace, policy_path, log_path)
    """
    base = Path(base_dir)
    workspace = base / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "output").mkdir(exist_ok=True)

    # Write sample files
    (workspace / "data.txt").write_text(SAMPLE_DATA_TXT)
    (workspace / "sales.csv").write_text(SAMPLE_SALES_CSV)

    # Write policy
    policy_path = base / "policy.yaml"
    policy_path.write_text(POLICY_TEMPLATE.format(workspace=str(workspace)))

    log_path = base / "kernel.log"
    return workspace, policy_path, log_path


def configure_llm() -> tuple[str, str]:
    """Read LLM configuration from environment variables.

    Environment variables:
        AGENT_MODEL   — model name    (default: gpt-5.4-mini)
        AGENT_API_KEY — API key       (default: built-in demo key)
        AGENT_API_BASE — API base URL (default: openai-proxy endpoint)

    Returns:
        (model, api_key)
    """
    api_key = os.environ.get("AGENT_API_KEY", DEFAULT_API_KEY)
    base_url = os.environ.get("AGENT_API_BASE", DEFAULT_BASE_URL)
    model = os.environ.get("AGENT_MODEL", DEFAULT_MODEL)

    litellm.api_base = base_url
    return model, api_key


def print_result(result: ActionResult) -> None:
    """Pretty-print an ActionResult to stdout."""
    print(f"  status    : {result.status}")
    if result.data is not None:
        data_str = str(result.data)
        if len(data_str) > 120:
            data_str = data_str[:120] + "..."
        print(f"  data      : {data_str}")
    if result.error is not None:
        print(f"  error     : {result.error}")
    if result.record_id is not None:
        print(f"  record_id : {result.record_id}")


def print_audit_log(log_path: str | Path) -> None:
    """Read a JSONL audit log and print a formatted table.

    Args:
        log_path: Path to the kernel JSONL log file.
    """
    log = Log(log_path)
    records = log.read_all()

    if not records:
        print("  (no log entries)")
        return

    # Column widths
    hdr = f"  {'#':<3} {'timestamp':<28} {'action':<12} {'target':<30} {'status':<12} {'ms':>6}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for i, rec in enumerate(records, 1):
        ts = rec.timestamp[:23]  # trim to ms precision
        target = rec.target if len(rec.target) <= 28 else "..." + rec.target[-25:]
        ms = str(rec.duration_ms) if rec.duration_ms is not None else "-"
        print(f"  {i:<3} {ts:<28} {rec.action:<12} {target:<30} {rec.status:<12} {ms:>6}")
        if rec.error:
            print(f"      error: {rec.error}")
