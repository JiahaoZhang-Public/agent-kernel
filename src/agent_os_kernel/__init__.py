"""Agent OS Kernel — security boundary for agent-world interactions.

One API: submit(action_request) -> action_result
Three components: Policy, Gate, Log
Three invariants: all access through Gate, default deny, no silent actions
"""

__version__ = "0.4.0"

from agent_os_kernel.agent_loop import AgentLoop, ToolDef, run_agent_loop
from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest, ActionResult, Record
from agent_os_kernel.policy import CapabilityRule, Policy, load_policy
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
    SnapshotStrategy,
)

__all__ = [
    "ActionRequest",
    "ActionResult",
    "AgentLoop",
    "CapabilityRule",
    "FsWriteSnapshotStrategy",
    "Kernel",
    "Policy",
    "Record",
    "ReversibleActionLayer",
    "SnapshotStore",
    "SnapshotStrategy",
    "ToolDef",
    "load_policy",
    "run_agent_loop",
]
