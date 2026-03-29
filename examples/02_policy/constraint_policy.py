"""Constraint-based policy example.

Demonstrates the three-part matching in CapabilityRule: action + resource +
constraint. A rule allows net.http to httpbin.org but only for GET requests.

Run:
    python -m examples.02_policy.constraint_policy
    # or
    python examples/02_policy/constraint_policy.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.http import HttpProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log, print_result


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "kernel.log"

        # -- Policy: allow GET only to httpbin.org -----------------------------
        policy = Policy(
            capabilities=[
                CapabilityRule(
                    action="net.http",
                    resource="https://httpbin.org/**",
                    constraint={"method": "GET"},
                ),
            ]
        )

        print("Policy rule:")
        cap = policy.capabilities[0]
        print(f"  action     : {cap.action}")
        print(f"  resource   : {cap.resource}")
        print(f"  constraint : {cap.constraint}")
        print()

        # -- Demonstrate three-part matching -----------------------------------
        print("Three-part matching breakdown:")
        print()

        get_req = ActionRequest(
            action="net.http",
            target="https://httpbin.org/get",
            params={"method": "GET"},
        )
        print("  GET request to httpbin.org/get:")
        print(f"    action matches   : {cap.action_matches(get_req.action)}")
        print(f"    resource matches : {cap.resource_matches(get_req.target)}")
        print(f"    constraint matches: {cap.constraint_matches(get_req)}")
        print(f"    => policy allows : {policy.is_allowed(get_req)}")
        print()

        post_req = ActionRequest(
            action="net.http",
            target="https://httpbin.org/post",
            params={"method": "POST", "body": {"key": "value"}},
        )
        print("  POST request to httpbin.org/post:")
        print(f"    action matches   : {cap.action_matches(post_req.action)}")
        print(f"    resource matches : {cap.resource_matches(post_req.target)}")
        print(f"    constraint matches: {cap.constraint_matches(post_req)}")
        print(f"    => policy allows : {policy.is_allowed(post_req)}")
        print()

        other_req = ActionRequest(
            action="net.http",
            target="https://evil.example.com/steal",
            params={"method": "GET"},
        )
        print("  GET request to evil.example.com:")
        print(f"    action matches   : {cap.action_matches(other_req.action)}")
        print(f"    resource matches : {cap.resource_matches(other_req.target)}")
        print(f"    => policy allows : {policy.is_allowed(other_req)}")
        print()

        # -- Submit through kernel to see real DENIED / OK results -------------
        print("=" * 60)
        print("Submitting through Kernel:")
        print()

        with Kernel(
            policy=policy,
            providers=[HttpProvider()],
            log_path=log_path,
        ) as kernel:
            # GET -> OK
            print("1) GET https://httpbin.org/get")
            r1 = kernel.submit(get_req)
            print_result(r1)
            print()

            # POST -> DENIED (constraint mismatch)
            print("2) POST https://httpbin.org/post (should be DENIED)")
            r2 = kernel.submit(post_req)
            print_result(r2)
            print()

            # GET to wrong host -> DENIED (resource mismatch)
            print("3) GET https://evil.example.com (should be DENIED)")
            r3 = kernel.submit(other_req)
            print_result(r3)
            print()

        # -- Audit log ---------------------------------------------------------
        print("=" * 60)
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
