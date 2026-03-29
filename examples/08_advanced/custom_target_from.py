#!/usr/bin/env python3
"""Callable target_from in ToolDef: dynamic target resolution.

Demonstrates using a callable (lambda or function) as ToolDef.target_from
instead of a static string key. The callable receives the tool arguments
dict and returns a computed target string. This is useful for tools like
MCP bridges where the target depends on multiple argument values.

No LLM required.

Run:
    uv run python examples/08_advanced/custom_target_from.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import print_audit_log

from agent_os_kernel import ActionRequest, Kernel, ToolDef
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.base import Provider

# ── Inline EchoProvider ──────────────────────────────────────────────


class EchoProvider(Provider):
    """Echoes back the request target and params for inspection."""

    @property
    def actions(self) -> list[str]:
        return ["echo.say"]

    def execute(self, request: ActionRequest) -> Any:
        return {"resolved_target": request.target, "params": request.params}


# ── ToolDef with callable target_from ────────────────────────────────

# Instead of target_from="path" (string key), use a callable that
# composes the target from multiple argument fields.
mcp_call_tool = ToolDef(
    name="mcp_call",
    description="Call an MCP server tool.",
    parameters={
        "type": "object",
        "properties": {
            "server": {"type": "string"},
            "tool": {"type": "string"},
            "arguments": {"type": "object"},
        },
        "required": ["server", "tool"],
    },
    action="echo.say",
    target_from=lambda args: f"{args.get('server', 'unknown')}/{args.get('tool', 'unknown')}",
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "kernel.log"

        # Allow echo.say to any target
        policy = Policy(
            capabilities=[
                CapabilityRule(action="echo.say", resource="*"),
            ]
        )

        with Kernel(policy=policy, providers=[EchoProvider()], log_path=log_path) as kernel:
            # ── Show how the callable target_from works ──────────────
            print("ToolDef configuration:")
            print(f"  name        : {mcp_call_tool.name}")
            print(f"  action      : {mcp_call_tool.action}")
            print(f"  target_from : {mcp_call_tool.target_from}")
            print()

            # Demonstrate different argument combinations
            test_cases: list[dict[str, Any]] = [
                {"server": "weather", "tool": "get_forecast", "arguments": {"city": "Tokyo"}},
                {"server": "db", "tool": "query", "arguments": {"sql": "SELECT 1"}},
                {"server": "slack", "tool": "post_message", "arguments": {"channel": "#general"}},
                {"tool": "orphan_call"},  # missing server -> "unknown"
            ]

            print("Resolving targets from different argument combinations:")
            print("=" * 60)

            for i, args in enumerate(test_cases, 1):
                # Resolve target using the callable — same logic AgentLoop uses
                assert callable(mcp_call_tool.target_from)
                target = mcp_call_tool.target_from(args)

                print(f"\n{i}) args: {args}")
                print(f"   resolved target: {target!r}")

                # Submit through kernel to prove it works end-to-end
                result = kernel.submit(
                    ActionRequest(
                        action="echo.say",
                        target=target,
                        params=args,
                    )
                )
                print(f"   status: {result.status}")
                print(f"   echoed target: {result.data['resolved_target']}")

                assert result.status == "OK"
                assert result.data["resolved_target"] == target

            # ── Compare with string-based target_from ────────────────
            print("\n" + "=" * 60)
            print("Comparison: string vs callable target_from")
            print()

            string_tool = ToolDef(
                name="read_file",
                description="Read a file.",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}},
                action="echo.say",
                target_from="path",  # string: looks up args["path"]
            )

            sample_args: dict[str, str] = {"path": "/data/report.txt"}
            # String target_from: uses the key to look up in args
            assert isinstance(string_tool.target_from, str)
            string_target = str(sample_args.get(string_tool.target_from, string_tool.name))
            # Callable target_from: calls the function with args
            assert callable(mcp_call_tool.target_from)
            callable_target = mcp_call_tool.target_from({"server": "files", "tool": "read"})

            print(f"  string target_from='path'  + args={sample_args}")
            print(f"    => target: {string_target!r}")
            print()
            print("  callable target_from(args) + args={'server': 'files', 'tool': 'read'}")
            print(f"    => target: {callable_target!r}")

        # ── Audit log ────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("Audit log:")
        print_audit_log(log_path)

        print("\nSuccess: callable target_from resolved all targets correctly.")


if __name__ == "__main__":
    main()
