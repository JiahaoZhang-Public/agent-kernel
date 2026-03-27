"""The Agent OS Kernel — Gate implementation.

Per v2 design §4 and §10: the Kernel is a single class with one API: submit().
It validates, authorizes, dispatches to a provider, logs, and returns.
Every path produces exactly one log entry. There are no silent paths.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_os_kernel.log import Log
from agent_os_kernel.models import ActionRequest, ActionResult, Record
from agent_os_kernel.policy import Policy, load_policy
from agent_os_kernel.providers.base import Provider


class Kernel:
    """The Agent OS Kernel.

    One API: submit(action_request) -> action_result
    Three components: Policy, Gate (this class), Log
    Three invariants: all access through Gate, default deny, no silent actions
    """

    def __init__(
        self,
        policy: str | Path | Policy,
        providers: dict[str, Provider] | list[Provider] | None = None,
        log_path: str | Path = "kernel.log",
    ) -> None:
        """Initialize the kernel.

        Args:
            policy: Path to YAML policy file, or a Policy instance.
            providers: Provider registry. Either a dict mapping action types
                to providers, or a list of providers (auto-registered by
                their declared action types).
            log_path: Path to the JSONL log file.
        """
        if isinstance(policy, Policy):
            self._policy = policy
        else:
            self._policy = load_policy(policy)

        self._providers: dict[str, Provider] = {}
        if providers is not None:
            if isinstance(providers, dict):
                self._providers = dict(providers)
            else:
                for provider in providers:
                    for action in provider.actions:
                        self._providers[action] = provider

        self._log = Log(log_path)
        self._log.open()

    def submit(self, request: ActionRequest) -> ActionResult:
        """Submit an action request through the Gate.

        Per v2 §4.2:
        1. Validate request format
        2. Match request against policy (default deny)
        3. Resolve provider for action
        4. Call provider.execute(request)
        5. Log result
        6. Return result

        Every path produces exactly one log record.
        """
        # 1. Validate
        if not request.validate():
            self._record(request, "INVALID")
            return ActionResult(status="ERROR", data=None, error="malformed request")

        # 2. Authorize
        if not self._policy.is_allowed(request):
            self._record(request, "DENIED")
            return ActionResult(status="DENIED", data=None, error="not permitted")

        # 3. Resolve provider
        provider = self._providers.get(request.action)
        if provider is None:
            self._record(request, "NO_PROVIDER")
            return ActionResult(status="ERROR", data=None, error="no provider")

        # 4. Execute
        start = time.monotonic()
        try:
            result = provider.execute(request)
            duration_ms = int((time.monotonic() - start) * 1000)
            self._record(request, "OK", duration_ms=duration_ms)
            return ActionResult(status="OK", data=result, error=None)
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            self._record(request, "FAILED", error=str(e), duration_ms=duration_ms)
            return ActionResult(status="ERROR", data=None, error=str(e))

    def close(self) -> None:
        """Close the kernel and its log."""
        self._log.close()

    @property
    def policy(self) -> Policy:
        """Access the kernel's policy (read-only)."""
        return self._policy

    @property
    def log(self) -> Log:
        """Access the kernel's log (read-only)."""
        return self._log

    def _record(
        self,
        request: ActionRequest,
        status: str,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Write a single log record."""
        record = Record(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=request.action,
            target=request.target,
            status=status,
            error=error,
            duration_ms=duration_ms,
        )
        self._log.write(record)

    def __enter__(self) -> Kernel:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
