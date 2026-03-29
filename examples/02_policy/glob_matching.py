"""Glob resource pattern matching example.

Demonstrates how CapabilityRule.resource_matches() handles different
glob patterns without requiring a full Kernel instance.

Run:
    python -m examples.02_policy.glob_matching
    # or
    python examples/02_policy/glob_matching.py
"""

from __future__ import annotations

from agent_os_kernel.policy import CapabilityRule


def main() -> None:
    # -- Define rules with different glob patterns -----------------------------
    rules: list[tuple[str, CapabilityRule]] = [
        ("single-star", CapabilityRule(action="fs.read", resource="/data/*")),
        ("recursive wildcard", CapabilityRule(action="fs.read", resource="/data/**")),
        ("extension match", CapabilityRule(action="fs.read", resource="/data/reports/*.csv")),
        ("exact path", CapabilityRule(action="fs.read", resource="/data/config.yaml")),
    ]

    # -- Paths to test against each rule ---------------------------------------
    test_paths = [
        "/data/file.txt",
        "/data/sub/file.txt",
        "/data/sub/deep/file.txt",
        "/data/reports/q1.csv",
        "/data/reports/q1.xlsx",
        "/data/reports/archive/q1.csv",
        "/data/config.yaml",
        "/data/config.json",
        "/other/file.txt",
    ]

    # -- Print truth table -----------------------------------------------------
    # Header
    col_w = 32
    labels = [name for name, _ in rules]
    header = f"  {'path':<{col_w}}" + "".join(f" {lbl:^20}" for lbl in labels)
    print(header)
    print("  " + "-" * (len(header) - 2))

    for path in test_paths:
        row = f"  {path:<{col_w}}"
        for _, rule in rules:
            match = rule.resource_matches(path)
            symbol = "YES" if match else " - "
            row += f" {symbol:^20}"
        print(row)

    print()

    # -- Detailed examples with explanations -----------------------------------
    print("Detailed pattern explanations:")
    print()

    print("  /data/*  (single-star wildcard)")
    print("    With fnmatch, * matches everything including path separators.")
    rule_one = CapabilityRule(action="fs.read", resource="/data/*")
    print(f"    /data/file.txt          -> {rule_one.resource_matches('/data/file.txt')}")
    print(f"    /data/sub/file.txt      -> {rule_one.resource_matches('/data/sub/file.txt')}")
    print()

    print("  /data/** (recursive wildcard)")
    print("    Matches files at any depth under /data/.")
    rule_rec = CapabilityRule(action="fs.read", resource="/data/**")
    print(f"    /data/file.txt          -> {rule_rec.resource_matches('/data/file.txt')}")
    print(f"    /data/sub/file.txt      -> {rule_rec.resource_matches('/data/sub/file.txt')}")
    print(f"    /data/sub/deep/file.txt -> {rule_rec.resource_matches('/data/sub/deep/file.txt')}")
    print(f"    /other/file.txt         -> {rule_rec.resource_matches('/other/file.txt')}")
    print()

    print("  /data/reports/*.csv (extension match)")
    print("    Matches .csv files; fnmatch * crosses path separators.")
    rule_csv = CapabilityRule(action="fs.read", resource="/data/reports/*.csv")
    print(f"    /data/reports/q1.csv    -> {rule_csv.resource_matches('/data/reports/q1.csv')}")
    print(f"    /data/reports/q1.xlsx   -> {rule_csv.resource_matches('/data/reports/q1.xlsx')}")
    print()

    print("  /data/config.yaml (exact path)")
    print("    Matches only the exact path specified.")
    rule_exact = CapabilityRule(action="fs.read", resource="/data/config.yaml")
    print(f"    /data/config.yaml       -> {rule_exact.resource_matches('/data/config.yaml')}")
    print(f"    /data/config.json       -> {rule_exact.resource_matches('/data/config.json')}")


if __name__ == "__main__":
    main()
