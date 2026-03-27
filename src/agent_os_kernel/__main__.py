"""CLI entry point for the Agent OS Kernel.

Usage:
    python -m agent_os_kernel submit --policy policy.yaml --action fs.read --target /path/to/file
    python -m agent_os_kernel log --log-path kernel.log
    python -m agent_os_kernel validate-policy --policy policy.yaml
    python -m agent_os_kernel version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agent_os_kernel import __version__
from agent_os_kernel.kernel import Kernel
from agent_os_kernel.log import Log
from agent_os_kernel.models import ActionRequest
from agent_os_kernel.policy import load_policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.http import HttpProvider
from agent_os_kernel.providers.process import ProcessProvider


def _default_providers() -> list[Any]:
    """Create default provider set."""
    return [FilesystemProvider(), ProcessProvider(), HttpProvider()]


def cmd_submit(args: argparse.Namespace) -> int:
    """Execute a single action through the kernel."""
    params: dict[str, Any] = {}
    if args.params:
        params = json.loads(args.params)

    log_path = args.log_path or "kernel.log"
    with Kernel(
        policy=args.policy,
        providers=_default_providers(),
        log_path=log_path,
    ) as kernel:
        request = ActionRequest(action=args.action, target=args.target, params=params)
        result = kernel.submit(request)

    output = {
        "status": result.status,
        "data": result.data,
        "error": result.error,
    }
    print(json.dumps(output, indent=2, default=str))
    return 0 if result.status == "OK" else 1


def cmd_log(args: argparse.Namespace) -> int:
    """Display kernel log entries."""
    log_path = Path(args.log_path)
    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        return 1

    log = Log(log_path)
    records = log.read_all()

    if args.status:
        records = [r for r in records if r.status == args.status.upper()]

    if args.action:
        records = [r for r in records if r.action == args.action]

    limit = args.limit or len(records)
    for record in records[-limit:]:
        entry: dict[str, Any] = {
            "timestamp": record.timestamp,
            "action": record.action,
            "target": record.target,
            "status": record.status,
        }
        if record.error:
            entry["error"] = record.error
        if record.duration_ms is not None:
            entry["duration_ms"] = record.duration_ms
        print(json.dumps(entry))

    return 0


def cmd_validate_policy(args: argparse.Namespace) -> int:
    """Validate a policy YAML file."""
    try:
        policy = load_policy(args.policy)
        print(f"Policy valid: {len(policy.capabilities)} capability rules loaded")
        for rule in policy.capabilities:
            constraint_str = f" (constraint: {rule.constraint})" if rule.constraint else ""
            print(f"  - {rule.action} on {rule.resource}{constraint_str}")
        return 0
    except Exception as e:
        print(f"Policy invalid: {e}", file=sys.stderr)
        return 1


def cmd_version(_args: argparse.Namespace) -> int:
    """Print version information."""
    print(f"agent-os-kernel {__version__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI main entry point."""
    parser = argparse.ArgumentParser(
        prog="agent-os-kernel",
        description="Agent OS Kernel — security boundary for agent-world interactions",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # submit
    sub = subparsers.add_parser("submit", help="Submit an action through the kernel")
    sub.add_argument("--policy", required=True, help="Path to YAML policy file")
    sub.add_argument("--action", required=True, help="Action type (e.g. fs.read)")
    sub.add_argument("--target", required=True, help="Action target")
    sub.add_argument("--params", help="JSON string of action parameters")
    sub.add_argument("--log-path", help="Path to log file (default: kernel.log)")
    sub.set_defaults(func=cmd_submit)

    # log
    sub = subparsers.add_parser("log", help="Display kernel log entries")
    sub.add_argument("--log-path", default="kernel.log", help="Path to log file")
    sub.add_argument("--status", help="Filter by status (OK, DENIED, etc.)")
    sub.add_argument("--action", dest="action", help="Filter by action type")
    sub.add_argument("--limit", type=int, help="Show last N entries")
    sub.set_defaults(func=cmd_log)

    # validate-policy
    sub = subparsers.add_parser("validate-policy", help="Validate a policy YAML file")
    sub.add_argument("--policy", required=True, help="Path to YAML policy file")
    sub.set_defaults(func=cmd_validate_policy)

    # version
    sub = subparsers.add_parser("version", help="Print version information")
    sub.set_defaults(func=cmd_version)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    ret: int = args.func(args)
    return ret


if __name__ == "__main__":
    sys.exit(main())
