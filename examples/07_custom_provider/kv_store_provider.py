#!/usr/bin/env python3
"""In-memory key-value store provider with kv.get, kv.set, kv.delete.

Demonstrates a stateful custom provider that maintains an internal dict
and exposes CRUD operations through the kernel Gate. The policy uses a
glob pattern to allow all kv.* actions.

No LLM required.

Run:
    uv run python examples/07_custom_provider/kv_store_provider.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.base import Provider


class KVStoreProvider(Provider):
    """In-memory key-value store provider."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    @property
    def actions(self) -> list[str]:
        return ["kv.get", "kv.set", "kv.delete"]

    def execute(self, request: ActionRequest) -> Any:
        if request.action == "kv.set":
            self._store[request.target] = request.params["value"]
            return {"stored": True}
        elif request.action == "kv.get":
            if request.target not in self._store:
                raise KeyError(f"Key not found: {request.target}")
            return {"value": self._store[request.target]}
        elif request.action == "kv.delete":
            if request.target not in self._store:
                raise KeyError(f"Key not found: {request.target}")
            del self._store[request.target]
            return {"deleted": True}
        else:
            raise ValueError(f"Unknown action: {request.action}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        policy = Policy(
            capabilities=[
                CapabilityRule(action="kv.set", resource="*"),
                CapabilityRule(action="kv.get", resource="*"),
                CapabilityRule(action="kv.delete", resource="*"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, providers=[KVStoreProvider()], log_path=log_path) as kernel:
            # SET
            r = kernel.submit(
                ActionRequest(
                    action="kv.set",
                    target="user:1",
                    params={"value": {"name": "Alice", "role": "admin"}},
                )
            )
            print(f"SET  user:1   -> {r.status}: {r.data}")

            r = kernel.submit(
                ActionRequest(
                    action="kv.set",
                    target="user:2",
                    params={"value": {"name": "Bob", "role": "viewer"}},
                )
            )
            print(f"SET  user:2   -> {r.status}: {r.data}")

            # GET
            r = kernel.submit(
                ActionRequest(
                    action="kv.get",
                    target="user:1",
                    params={},
                )
            )
            print(f"GET  user:1   -> {r.status}: {r.data}")
            assert r.data["value"]["name"] == "Alice"

            # DELETE
            r = kernel.submit(
                ActionRequest(
                    action="kv.delete",
                    target="user:2",
                    params={},
                )
            )
            print(f"DEL  user:2   -> {r.status}: {r.data}")

            # GET after delete (should fail)
            r = kernel.submit(
                ActionRequest(
                    action="kv.get",
                    target="user:2",
                    params={},
                )
            )
            print(f"GET  user:2   -> {r.status}: {r.error}")
            assert r.status == "ERROR"

            print("\nSuccess: KVStoreProvider CRUD sequence completed.")


if __name__ == "__main__":
    main()
