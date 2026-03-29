#!/usr/bin/env python3
"""Chain two providers: HTTP GET -> filesystem write.

Run: uv run python examples/06_multi_provider/fetch_and_save.py
"""

import json
import sys
import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.http import HttpProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log, print_result


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Policy: allow HTTP GET to httpbin.org, and fs read/write in workspace
        policy = Policy(
            capabilities=[
                CapabilityRule(
                    action="net.http",
                    resource="https://httpbin.org/**",
                    constraint={"method": "GET"},
                ),
                CapabilityRule(action="fs.write", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[HttpProvider(), FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            # -- Step 1: GET a random UUID from httpbin -------------------------
            print("1) GET https://httpbin.org/uuid")
            r1 = kernel.submit(
                ActionRequest(
                    action="net.http",
                    target="https://httpbin.org/uuid",
                    params={"method": "GET"},
                )
            )
            print_result(r1)
            assert r1.status == "OK", f"HTTP GET failed: {r1.error}"

            body = json.loads(r1.data["body"])
            uuid_value = body["uuid"]
            print(f"  extracted : {uuid_value}")
            print()

            # -- Step 2: Write UUID to output/uuid.txt --------------------------
            output_file = workspace / "output" / "uuid.txt"
            print(f"2) fs.write -> {output_file}")
            r2 = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(output_file),
                    params={"content": uuid_value},
                )
            )
            print_result(r2)
            assert r2.status == "OK", f"fs.write failed: {r2.error}"
            print()

            # -- Step 3: Read it back and confirm match -------------------------
            print(f"3) fs.read <- {output_file}")
            r3 = kernel.submit(
                ActionRequest(
                    action="fs.read",
                    target=str(output_file),
                )
            )
            print_result(r3)
            assert r3.status == "OK", f"fs.read failed: {r3.error}"

            read_back = r3.data
            assert read_back == uuid_value, f"Mismatch: wrote {uuid_value!r} but read {read_back!r}"
            print("  verified  : written and read values match")
            print()

        # -- Audit log ---------------------------------------------------------
        print("=" * 60)
        print("Audit log (3 actions: net.http, fs.write, fs.read):")
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
