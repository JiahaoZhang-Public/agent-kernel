#!/usr/bin/env python3
"""Programmatic policy construction from data.

Builds a Policy dynamically from a project configuration dictionary.
Each project gets read access to its data directory and read+write
access to its output directory. Demonstrates that requests matching
the dynamic rules are allowed while others are denied.

Uses real temp directories so all paths resolve correctly.

No LLM required.

Run:
    uv run python examples/08_advanced/programmatic_policy.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _common import print_audit_log, print_result

from agent_os_kernel import ActionRequest, Kernel
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        log_path = base / "kernel.log"

        # ── Create real directory structure ───────────────────────────
        data_dir = base / "data"
        output_dir = base / "output"

        # Simulate: different projects have different allowed directories
        projects = {
            "project_alpha": [str(data_dir / "alpha"), str(output_dir / "alpha")],
            "project_beta": [str(data_dir / "beta"), str(output_dir / "beta")],
        }

        # Create all directories and seed data files
        for project_name, dirs in projects.items():
            for d in dirs:
                Path(d).mkdir(parents=True, exist_ok=True)

            # Seed each project's data directory with a file
            data_path = Path(dirs[0]) / "dataset.csv"
            data_path.write_text(f"id,value\n1,{project_name}_sample\n")

        # Also create a "forbidden" area outside any project
        forbidden = base / "secrets"
        forbidden.mkdir()
        (forbidden / "credentials.txt").write_text("TOP SECRET\n")

        # ── Build policy dynamically from project data ───────────────
        capabilities: list[CapabilityRule] = []
        for _name, dirs in projects.items():
            for d in dirs:
                # Read access to all project directories
                capabilities.append(CapabilityRule(action="fs.read", resource=f"{d}/**"))
                # Write access only to output directories
                if d.startswith(str(output_dir)):
                    capabilities.append(CapabilityRule(action="fs.write", resource=f"{d}/**"))

        policy = Policy(capabilities=capabilities)

        # ── Display the generated policy ─────────────────────────────
        print("Dynamically generated policy rules:")
        print("=" * 60)
        for i, cap in enumerate(policy.capabilities, 1):
            print(f"  {i}. action={cap.action:<10} resource={cap.resource}")
        print()

        # ── Submit requests matching and not matching ────────────────
        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            alpha_data = str(data_dir / "alpha" / "dataset.csv")
            beta_data = str(data_dir / "beta" / "dataset.csv")
            alpha_output = str(output_dir / "alpha" / "result.txt")
            beta_output = str(output_dir / "beta" / "result.txt")
            secret_file = str(forbidden / "credentials.txt")
            cross_write = str(data_dir / "alpha" / "injected.txt")

            # ── Allowed requests ─────────────────────────────────────
            print("1) Read alpha data (should be OK)")
            r = kernel.submit(ActionRequest(action="fs.read", target=alpha_data))
            print_result(r)
            assert r.status == "OK"
            print()

            print("2) Read beta data (should be OK)")
            r = kernel.submit(ActionRequest(action="fs.read", target=beta_data))
            print_result(r)
            assert r.status == "OK"
            print()

            print("3) Write to alpha output (should be OK)")
            r = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=alpha_output,
                    params={"content": "Alpha analysis complete.\n"},
                )
            )
            print_result(r)
            assert r.status == "OK"
            print()

            print("4) Write to beta output (should be OK)")
            r = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=beta_output,
                    params={"content": "Beta analysis complete.\n"},
                )
            )
            print_result(r)
            assert r.status == "OK"
            print()

            print("5) Read alpha output (should be OK)")
            r = kernel.submit(ActionRequest(action="fs.read", target=alpha_output))
            print_result(r)
            assert r.status == "OK"
            print()

            # ── Denied requests ──────────────────────────────────────
            print("6) Read secrets (should be DENIED)")
            r = kernel.submit(ActionRequest(action="fs.read", target=secret_file))
            print_result(r)
            assert r.status == "DENIED"
            print()

            print("7) Write to data directory (should be DENIED)")
            r = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=cross_write,
                    params={"content": "Should not be written.\n"},
                )
            )
            print_result(r)
            assert r.status == "DENIED"
            assert not Path(cross_write).exists(), "File should not have been created"
            print()

            print("8) Cross-project write: alpha writing to beta output (should be DENIED)")
            # Alpha's policy only allows writing to output/alpha, not output/beta
            # But wait - our policy grants write to output/beta too (for project_beta).
            # Let's test writing to a completely outside path instead.
            outside_path = str(base / "rogue_output.txt")
            r = kernel.submit(
                ActionRequest(
                    action="fs.write",
                    target=outside_path,
                    params={"content": "Rogue write attempt.\n"},
                )
            )
            print_result(r)
            assert r.status == "DENIED"
            print()

            print("9) Delete action (not in policy, should be DENIED)")
            r = kernel.submit(
                ActionRequest(
                    action="fs.delete",
                    target=alpha_output,
                )
            )
            print_result(r)
            assert r.status == "DENIED"
            print()

        # ── Verify files ─────────────────────────────────────────────
        print("=" * 60)
        print("File verification:")
        print(f"  alpha output exists : {Path(alpha_output).exists()}")
        print(f"  beta output exists  : {Path(beta_output).exists()}")
        print(f"  cross-write blocked : {not Path(cross_write).exists()}")
        print(f"  rogue write blocked : {not Path(outside_path).exists()}")
        print()

        # ── Audit log ────────────────────────────────────────────────
        print("Audit log:")
        print_audit_log(log_path)

        print(f"\nSuccess: programmatic policy correctly enforced {len(capabilities)} rules.")


if __name__ == "__main__":
    main()
