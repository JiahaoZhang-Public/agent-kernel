"""Policy engine for the Agent OS Kernel.

Loads a static YAML allow-list and matches action requests against it.
Per v2 design §3: default deny, explicit allow, glob-based resource matching.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agent_os_kernel.models import ActionRequest


@dataclass
class CapabilityRule:
    """A single capability rule from the policy file.

    Attributes:
        action: The action type being permitted, e.g. "fs.read".
        resource: The resource pattern being permitted, e.g. "/workspace/**".
        constraint: Optional additional restrictions, e.g. {"method": "GET"}.
    """

    action: str
    resource: str
    constraint: dict[str, Any] | None = None

    def action_matches(self, action: str) -> bool:
        """Check if the requested action matches this rule's action type."""
        return self.action == action

    def resource_matches(self, target: str) -> bool:
        """Check if the requested target matches this rule's resource pattern.

        Uses glob-style matching: ** matches everything including path separators.
        """
        return fnmatch.fnmatch(target, self.resource)

    def constraint_matches(self, request: ActionRequest) -> bool:
        """Check if the request satisfies this rule's constraints."""
        if self.constraint is None:
            return True
        return all(request.params.get(key) == value for key, value in self.constraint.items())


@dataclass
class Policy:
    """A set of capability rules loaded from a YAML file.

    Policy is a static allow-list. If no rule matches, the action is denied.
    """

    capabilities: list[CapabilityRule] = field(default_factory=list)

    def is_allowed(self, request: ActionRequest) -> bool:
        """Check if a request is permitted by any capability rule.

        Per v2 §3.3: iterate rules, check action + resource + constraint.
        Default deny if no rule matches.
        """
        for cap in self.capabilities:
            if (
                cap.action_matches(request.action)
                and cap.resource_matches(request.target)
                and cap.constraint_matches(request)
            ):
                return True
        return False


def load_policy(policy_path: str | Path) -> Policy:
    """Load a policy from a YAML file.

    Expected format:
        capabilities:
          - action: fs.read
            resource: /workspace/**
          - action: fs.write
            resource: /workspace/output/**

    Args:
        policy_path: Path to the YAML policy file.

    Returns:
        A Policy instance with the parsed capability rules.

    Raises:
        FileNotFoundError: If the policy file does not exist.
        ValueError: If the policy file is malformed.
    """
    path = Path(policy_path)
    with path.open() as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "capabilities" not in data:
        raise ValueError(f"Policy file must contain 'capabilities' key: {policy_path}")

    capabilities: list[CapabilityRule] = []
    for rule in data["capabilities"]:
        if not isinstance(rule, dict) or "action" not in rule or "resource" not in rule:
            raise ValueError(f"Each capability must have 'action' and 'resource': {rule}")
        capabilities.append(
            CapabilityRule(
                action=rule["action"],
                resource=rule["resource"],
                constraint=rule.get("constraint"),
            )
        )

    return Policy(capabilities=capabilities)
