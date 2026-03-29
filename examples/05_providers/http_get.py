"""HTTP GET example.

Demonstrates making an HTTP GET request through the Kernel using
HttpProvider with a policy that allows GET to httpbin.org.

Run:
    python -m examples.05_providers.http_get
    # or
    python examples/05_providers/http_get.py
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

        # Policy: allow GET requests to httpbin.org
        policy = Policy(
            capabilities=[
                CapabilityRule(
                    action="net.http",
                    resource="https://httpbin.org/**",
                    constraint={"method": "GET"},
                ),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[HttpProvider()],
            log_path=log_path,
        ) as kernel:
            # -- Simple GET ----------------------------------------------------
            print("1) GET https://httpbin.org/get")
            r1 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://httpbin.org/get",
                    params={"method": "GET"},
                )
            )
            print_result(r1)

            # Parse and show response details
            if r1.status == "OK" and r1.data:
                print()
                print("  Response details:")
                print(f"    status_code : {r1.data['status_code']}")
                body = json.loads(r1.data["body"])
                print(f"    origin      : {body.get('origin', 'N/A')}")
                print(f"    url         : {body.get('url', 'N/A')}")
            print()

            # -- GET with query parameters (encoded in URL) --------------------
            print("2) GET https://httpbin.org/get?name=agent&version=0.4")
            r2 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://httpbin.org/get?name=agent&version=0.4",
                    params={"method": "GET"},
                )
            )
            print_result(r2)

            if r2.status == "OK" and r2.data:
                print()
                print("  Query params echoed back:")
                body = json.loads(r2.data["body"])
                for key, val in body.get("args", {}).items():
                    print(f"    {key} = {val}")
            print()

            # -- GET with custom headers ---------------------------------------
            print("3) GET with custom headers")
            r3 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://httpbin.org/headers",
                    params={
                        "method": "GET",
                        "headers": {"X-Agent-Id": "kernel-demo", "Accept": "application/json"},
                    },
                )
            )
            print_result(r3)

            if r3.status == "OK" and r3.data:
                print()
                print("  Custom headers echoed:")
                body = json.loads(r3.data["body"])
                headers = body.get("headers", {})
                for key in ["X-Agent-Id", "Accept"]:
                    print(f"    {key}: {headers.get(key, 'N/A')}")
            print()

        # -- Audit log ---------------------------------------------------------
        print("=" * 60)
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
