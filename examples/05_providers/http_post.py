"""HTTP POST example.

Demonstrates making an HTTP POST request with a JSON body through
the Kernel using HttpProvider.

Run:
    python -m examples.05_providers.http_post
    # or
    python examples/05_providers/http_post.py
"""

from __future__ import annotations

import json
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

        # Policy: allow both GET and POST to httpbin.org
        policy = Policy(
            capabilities=[
                CapabilityRule(
                    action="net.http",
                    resource="https://httpbin.org/**",
                    constraint={"method": "GET"},
                ),
                CapabilityRule(
                    action="net.http",
                    resource="https://httpbin.org/**",
                    constraint={"method": "POST"},
                ),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[HttpProvider()],
            log_path=log_path,
        ) as kernel:
            # -- POST with JSON body -------------------------------------------
            print("1) POST https://httpbin.org/post with JSON body")
            payload = {
                "task": "analyze",
                "data": [1, 2, 3],
                "options": {"verbose": True},
            }
            r1 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://httpbin.org/post",
                    params={
                        "method": "POST",
                        "body": payload,
                        "headers": {"Content-Type": "application/json"},
                    },
                )
            )
            print_result(r1)

            if r1.status == "OK" and r1.data:
                print()
                print("  Response details:")
                print(f"    status_code : {r1.data['status_code']}")
                body = json.loads(r1.data["body"])
                print(f"    echoed json : {body.get('json')}")
                print(f"    url         : {body.get('url')}")
            print()

            # -- POST with form-like data --------------------------------------
            print("2) POST with a simple key-value body")
            r2 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://httpbin.org/post",
                    params={
                        "method": "POST",
                        "body": {"username": "agent", "action": "login"},
                        "headers": {"Content-Type": "application/json"},
                    },
                )
            )
            print_result(r2)

            if r2.status == "OK" and r2.data:
                print()
                body = json.loads(r2.data["body"])
                print(f"  Echoed data: {body.get('json')}")
            print()

            # -- Verify GET still works ----------------------------------------
            print("3) GET (verify policy allows both methods)")
            r3 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://httpbin.org/get",
                    params={"method": "GET"},
                )
            )
            print_result(r3)
            print()

            # -- POST to disallowed host -> DENIED -----------------------------
            print("4) POST to disallowed host (should be DENIED)")
            r4 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://example.com/api",
                    params={
                        "method": "POST",
                        "body": {"secret": "data"},
                    },
                )
            )
            print_result(r4)
            print()

        # -- Audit log ---------------------------------------------------------
        print("=" * 60)
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
