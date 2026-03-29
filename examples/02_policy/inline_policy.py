"""Inline policy configuration example.

Demonstrates creating a Policy entirely in Python (no YAML file needed)
and submitting requests that exercise each capability rule.

Run:
    python -m examples.02_policy.inline_policy
    # or
    python examples/02_policy/inline_policy.py
"""

from __future__ import annotations

# Import shared helpers for pretty-printing
import sys
import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log, print_result


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        (workspace / "output").mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # -- Create policy entirely in Python ----------------------------------
        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{workspace}/**"),
                CapabilityRule(action="fs.write", resource=f"{workspace}/output/**"),
                CapabilityRule(action="fs.delete", resource=f"{workspace}/output/**"),
            ]
        )

        # Seed a file to read
        (workspace / "data.txt").write_text("Hello from the workspace!\n")

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            # 1. fs.read inside workspace -> OK
            print("1) Read file inside workspace")
            r1 = kernel.submit(
                ActionRequest(
                    action="fs.read",
                    target=str(workspace / "data.txt"),
                )
            )
            print_result(r1)
            print()

            # 2. fs.write to output/ -> OK
            print("2) Write file to output/")
            r2 = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(workspace / "output" / "result.txt"),
                    params={"content": "Analysis complete.\n"},
                )
            )
            print_result(r2)
            print()

            # 3. fs.write outside output/ -> DENIED
            print("3) Write file outside output/ (should be DENIED)")
            r3 = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(workspace / "unauthorized.txt"),
                    params={"content": "Should not be written.\n"},
                )
            )
            print_result(r3)
            # Verify the file was not created
            assert not (workspace / "unauthorized.txt").exists(), "File should not exist"
            print()

            # 4. fs.delete from output/ -> OK
            print("4) Delete file from output/")
            r4 = kernel.submit(
                ActionRequest(
                    action="fs.delete",
                    target=str(workspace / "output" / "result.txt"),
                )
            )
            print_result(r4)
            print()

            # -- Summary -------------------------------------------------------
            print("=" * 60)
            print("Audit log:")
            print_audit_log(log_path)


if __name__ == "__main__":
    main()
