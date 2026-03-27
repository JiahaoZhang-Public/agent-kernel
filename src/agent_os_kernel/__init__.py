"""Agent OS Kernel — security boundary for agent-world interactions.

One API: submit(action_request) -> action_result
Three components: Policy, Gate, Log
Three invariants: all access through Gate, default deny, no silent actions
"""

__version__ = "0.3.0"

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest, ActionResult, Record
from agent_os_kernel.policy import CapabilityRule, Policy, load_policy

__all__ = [
    "ActionRequest",
    "ActionResult",
    "CapabilityRule",
    "Kernel",
    "Policy",
    "Record",
    "load_policy",
]
