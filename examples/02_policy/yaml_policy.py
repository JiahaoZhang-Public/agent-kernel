"""YAML policy loading example.

Demonstrates loading policy rules from a YAML file and using both
the Kernel(policy=path) shorthand and the standalone load_policy() API.

Run:
    python -m examples.02_policy.yaml_policy
    # or
    python examples/02_policy/yaml_policy.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import load_policy
from agent_os_kernel.providers.filesystem import FilesystemProvider

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import print_audit_log, print_result

POLICY_YAML = """\
capabilities:
  - action: fs.read
    resource: "{workspace}/**"
  - action: fs.write
    resource: "{workspace}/output/**"
  - action: fs.delete
    resource: "{workspace}/output/**"
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        (workspace / "output").mkdir()
        log_path = Path(tmpdir) / "kernel.log"

        # Seed sample data
        (workspace / "notes.txt").write_text("Important notes go here.\n")

        # -- Write YAML policy to a temp file ----------------------------------
        policy_path = Path(tmpdir) / "policy.yaml"
        policy_path.write_text(POLICY_YAML.format(workspace=str(workspace)))

        print(f"Policy file: {policy_path}")
        print(f"Contents:\n{policy_path.read_text()}")

        # -- Use load_policy() standalone to inspect the rules -----------------
        policy = load_policy(policy_path)
        print(f"Loaded {len(policy.capabilities)} rules from YAML:")
        for i, cap in enumerate(policy.capabilities, 1):
            constraint_str = f", constraint={cap.constraint}" if cap.constraint else ""
            print(f"  {i}. action={cap.action}, resource={cap.resource}{constraint_str}")
        print()

        # -- Create Kernel with file path string (auto-loads YAML) -------------
        with Kernel(
            policy=str(policy_path),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            # Read -> OK
            print("1) Read file via YAML-loaded policy")
            r1 = kernel.submit(
                ActionRequest(
                    action="fs.read",
                    target=str(workspace / "notes.txt"),
                )
            )
            print_result(r1)
            print()

            # Write to output -> OK
            print("2) Write to output/")
            r2 = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(workspace / "output" / "report.txt"),
                    params={"content": "Generated report.\n"},
                )
            )
            print_result(r2)
            print()

            # Write outside output -> DENIED
            print("3) Write outside output/ (DENIED)")
            r3 = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(workspace / "hack.txt"),
                    params={"content": "nope"},
                )
            )
            print_result(r3)
            print()

        # -- Audit log ---------------------------------------------------------
        print("=" * 60)
        print("Audit log:")
        print_audit_log(log_path)


if __name__ == "__main__":
    main()
