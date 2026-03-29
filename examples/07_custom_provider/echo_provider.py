#!/usr/bin/env python3
"""Minimal custom provider: EchoProvider that echoes back request params.

Demonstrates how to build a custom provider by subclassing Provider,
registering it with the kernel, and submitting actions through the Gate.

No LLM required.

Run:
    uv run python examples/07_custom_provider/echo_provider.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.base import Provider


class EchoProvider(Provider):
    """A trivial provider that echoes back request params and target."""

    @property
    def actions(self) -> list[str]:
        return ["echo.say"]

    def execute(self, request: ActionRequest) -> Any:
        return {"echoed": request.params, "target": request.target}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        policy = Policy(
            capabilities=[
                CapabilityRule(action="echo.say", resource="*"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, providers=[EchoProvider()], log_path=log_path) as kernel:
            result = kernel.submit(
                ActionRequest(
                    action="echo.say",
                    target="world",
                    params={"greeting": "hello", "count": 3},
                )
            )

            print(f"status : {result.status}")
            print(f"data   : {result.data}")

            assert result.status == "OK"
            assert result.data["echoed"] == {"greeting": "hello", "count": 3}
            assert result.data["target"] == "world"
            print("\nSuccess: EchoProvider echoed params and target.")


if __name__ == "__main__":
    main()
