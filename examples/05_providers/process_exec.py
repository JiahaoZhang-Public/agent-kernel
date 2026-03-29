"""Process provider example — shell command execution.

Demonstrates running shell commands via ProcessProvider with a policy
that allows specific commands (echo, ls) and denies others (rm).

Run:
    python -m examples.05_providers.process_exec
    # or
    python examples/05_providers/process_exec.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.process import ProcessProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log, print_result


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "kernel.log"

        # Create a test directory with files for `ls`
        test_dir = Path(tmpdir) / "test_files"
        test_dir.mkdir()
        (test_dir / "alpha.txt").write_text("a")
        (test_dir / "beta.txt").write_text("b")
        (test_dir / "gamma.csv").write_text("c")

        # Policy: allow echo and ls, deny everything else
        policy = Policy(
            capabilities=[
                CapabilityRule(action="proc.exec", resource="echo"),
                CapabilityRule(action="proc.exec", resource="ls"),
            ]
        )

        with Kernel(
            policy=policy,
            providers=[ProcessProvider()],
            log_path=log_path,
        ) as kernel:
            # 1. echo hello world
            print("1) echo 'hello world'")
            r1 = kernel.submit(
                ActionRequest(
                    action="proc.exec",
                    target="echo",
                    params={"args": ["hello world"]},
                )
            )
            print_result(r1)
            print()

            # 2. ls the test directory
            print(f"2) ls {test_dir}")
            r2 = kernel.submit(
                ActionRequest(
                    action="proc.exec",
                    target="ls",
                    params={"args": [str(test_dir)]},
                )
            )
            print_result(r2)
            print()

            # 3. echo with multiple arguments
            print("3) echo with multiple args")
            r3 = kernel.submit(
                ActionRequest(
                    action="proc.exec",
                    target="echo",
                    params={"args": ["-n", "no newline output"]},
                )
            )
            print_result(r3)
            print()

            # 4. rm -> DENIED (not in policy)
            print("4) rm (should be DENIED)")
            r4 = kernel.submit(
                ActionRequest(
                    action="proc.exec",
                    target="rm",
                    params={"args": ["-rf", "/tmp/something"]},
                )
            )
            print_result(r4)
            print()

            # 5. cat -> DENIED (not in policy)
            print("5) cat (should be DENIED)")
            r5 = kernel.submit(
                ActionRequest(
                    action="proc.exec",
                    target="cat",
                    params={"args": ["/etc/passwd"]},
                )
            )
            print_result(r5)
            print()

        # -- Audit log ---------------------------------------------------------
        print("=" * 60)
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
