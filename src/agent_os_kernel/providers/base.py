"""Provider base class for the Agent OS Kernel.

Per v2 design §7: providers are the only components that touch the external world.
A provider declares which action types it handles, receives authorized requests
from the Gate, executes the real effect, and returns a result.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_os_kernel.models import ActionRequest


class Provider(ABC):
    """Abstract base class for all providers.

    A provider:
    - declares which action types it handles
    - receives an already-authorized request from the Gate
    - executes the real effect
    - returns a result or raises an exception

    A provider does NOT:
    - check authorization (the Gate already did)
    - write to the Log (the Gate does this)
    - call other providers
    - interact with the agent loop
    """

    @property
    @abstractmethod
    def actions(self) -> list[str]:
        """List of action types this provider handles."""
        ...

    @abstractmethod
    def execute(self, request: ActionRequest) -> Any:
        """Execute the action and return a result.

        Args:
            request: An already-authorized ActionRequest.

        Returns:
            The result of the action (provider-specific).

        Raises:
            Exception: If execution fails.
        """
        ...
