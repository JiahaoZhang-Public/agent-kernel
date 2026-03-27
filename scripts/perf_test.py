#!/usr/bin/env python3
"""Performance and load testing for the Agent OS Kernel.

Tests:
1. Sequential throughput — how many submit()s per second
2. Concurrent load — multiple threads hammering the kernel
3. Log integrity under load — verify no dropped/duplicated entries
4. Provider latency distribution — measure p50/p95/p99
5. Stress test — 1000+ actions with mixed allow/deny

Run from project root:
    python scripts/perf_test.py
"""

from __future__ import annotations

import statistics
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.log import Log
from agent_os_kernel.models import ActionRequest
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


@dataclass
class PerfResult:
    name: str
    total_ops: int
    duration_s: float
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def ops_per_sec(self) -> float:
        return self.total_ops / self.duration_s if self.duration_s > 0 else 0

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies_ms) if self.latencies_ms else 0

    @property
    def p95(self) -> float:
        if not self.latencies_ms:
            return 0
        s = sorted(self.latencies_ms)
        return s[int(len(s) * 0.95)]

    @property
    def p99(self) -> float:
        if not self.latencies_ms:
            return 0
        s = sorted(self.latencies_ms)
        return s[int(len(s) * 0.99)]

    def print(self) -> None:
        print(f"\n{'=' * 60}")
        print(f"  {self.name}")
        print(f"{'=' * 60}")
        print(f"  Total ops:    {self.total_ops}")
        print(f"  Duration:     {self.duration_s:.2f}s")
        print(f"  Throughput:   {self.ops_per_sec:.0f} ops/sec")
        print(f"  Errors:       {self.errors}")
        if self.latencies_ms:
            print(f"  Latency p50:  {self.p50:.2f} ms")
            print(f"  Latency p95:  {self.p95:.2f} ms")
            print(f"  Latency p99:  {self.p99:.2f} ms")
            print(f"  Latency min:  {min(self.latencies_ms):.2f} ms")
            print(f"  Latency max:  {max(self.latencies_ms):.2f} ms")


# ---------------------------------------------------------------------------
# Test 1: Sequential throughput (policy only, no I/O)
# ---------------------------------------------------------------------------


def test_sequential_throughput(n_ops: int = 2000) -> PerfResult:
    """Measure pure kernel submit() throughput (deny-only policy, no provider)."""
    with tempfile.TemporaryDirectory() as tmp:
        policy = Policy(capabilities=[])  # deny everything
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, log_path=log_path) as kernel:
            latencies = []
            start = time.monotonic()
            for _ in range(n_ops):
                t0 = time.monotonic()
                kernel.submit(ActionRequest(action="fs.read", target="/workspace/file.txt"))
                latencies.append((time.monotonic() - t0) * 1000)
            duration = time.monotonic() - start

        return PerfResult(
            name="Sequential throughput (deny-only)",
            total_ops=n_ops,
            duration_s=duration,
            latencies_ms=latencies,
        )


# ---------------------------------------------------------------------------
# Test 2: Sequential throughput with real provider (fs.read)
# ---------------------------------------------------------------------------


def test_sequential_with_provider(n_ops: int = 500) -> PerfResult:
    """Sequential reads from filesystem provider."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace"
        ws.mkdir()
        test_file = ws / "perf.txt"
        test_file.write_text("performance test content " * 100)

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            latencies = []
            start = time.monotonic()
            errors = 0
            for _ in range(n_ops):
                t0 = time.monotonic()
                result = kernel.submit(ActionRequest(action="fs.read", target=str(test_file)))
                latencies.append((time.monotonic() - t0) * 1000)
                if result.status != "OK":
                    errors += 1
            duration = time.monotonic() - start

        return PerfResult(
            name="Sequential throughput (fs.read with provider)",
            total_ops=n_ops,
            duration_s=duration,
            latencies_ms=latencies,
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Test 3: Concurrent load (multi-threaded)
# ---------------------------------------------------------------------------


def test_concurrent_load(n_threads: int = 10, ops_per_thread: int = 100) -> PerfResult:
    """Multiple threads submitting actions concurrently."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace"
        ws.mkdir()
        test_file = ws / "concurrent.txt"
        test_file.write_text("concurrent test data")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            all_latencies: list[float] = []
            all_errors = [0]
            lock = threading.Lock()

            def worker() -> None:
                local_latencies = []
                local_errors = 0
                for _ in range(ops_per_thread):
                    t0 = time.monotonic()
                    result = kernel.submit(ActionRequest(action="fs.read", target=str(test_file)))
                    local_latencies.append((time.monotonic() - t0) * 1000)
                    if result.status != "OK":
                        local_errors += 1
                with lock:
                    all_latencies.extend(local_latencies)
                    all_errors[0] += local_errors

            start = time.monotonic()
            threads = [threading.Thread(target=worker) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            duration = time.monotonic() - start

        total_ops = n_threads * ops_per_thread
        return PerfResult(
            name=f"Concurrent load ({n_threads} threads × {ops_per_thread} ops)",
            total_ops=total_ops,
            duration_s=duration,
            latencies_ms=all_latencies,
            errors=all_errors[0],
        )


# ---------------------------------------------------------------------------
# Test 4: Log integrity under concurrent load
# ---------------------------------------------------------------------------


def test_log_integrity_concurrent(n_threads: int = 8, ops_per_thread: int = 50) -> dict[str, object]:
    """Verify no log entries are dropped or duplicated under concurrent writes."""
    with tempfile.TemporaryDirectory() as tmp:
        policy = Policy(capabilities=[])
        log_path = Path(tmp) / "kernel.log"

        with Kernel(policy=policy, log_path=log_path) as kernel:

            def worker() -> None:
                for _ in range(ops_per_thread):
                    kernel.submit(ActionRequest(action="fs.read", target="/workspace/x"))

            threads = [threading.Thread(target=worker) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        records = Log(log_path).read_all()
        expected = n_threads * ops_per_thread
        return {
            "expected_entries": expected,
            "actual_entries": len(records),
            "integrity_ok": len(records) == expected,
        }


# ---------------------------------------------------------------------------
# Test 5: Mixed allow/deny stress test
# ---------------------------------------------------------------------------


def test_mixed_stress(n_ops: int = 1000) -> PerfResult:
    """Mixed allowed and denied actions at high volume."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace"
        ws.mkdir()
        (ws / "data.txt").write_text("data")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            latencies = []
            errors = 0
            start = time.monotonic()
            for i in range(n_ops):
                t0 = time.monotonic()
                if i % 3 == 0:
                    # Allowed
                    result = kernel.submit(ActionRequest(action="fs.read", target=str(ws / "data.txt")))
                elif i % 3 == 1:
                    # Denied (wrong action)
                    result = kernel.submit(
                        ActionRequest(action="fs.write", target=str(ws / "data.txt"), params={"content": "x"})
                    )
                else:
                    # Denied (out of scope)
                    result = kernel.submit(ActionRequest(action="fs.read", target="/etc/passwd"))
                latencies.append((time.monotonic() - t0) * 1000)
                if result.status == "ERROR":
                    errors += 1
            duration = time.monotonic() - start

        # Verify log completeness
        records = Log(log_path).read_all()
        assert len(records) == n_ops, f"Log integrity: expected {n_ops}, got {len(records)}"

        return PerfResult(
            name=f"Mixed allow/deny stress ({n_ops} ops)",
            total_ops=n_ops,
            duration_s=duration,
            latencies_ms=latencies,
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Test 6: Write throughput (creates many files)
# ---------------------------------------------------------------------------


def test_write_throughput(n_ops: int = 200) -> PerfResult:
    """Measure write throughput through kernel."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "workspace" / "output"
        ws.mkdir(parents=True)

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.write", resource=f"{ws}/**"),
            ]
        )
        log_path = Path(tmp) / "kernel.log"

        with Kernel(
            policy=policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as kernel:
            latencies = []
            errors = 0
            start = time.monotonic()
            for i in range(n_ops):
                t0 = time.monotonic()
                result = kernel.submit(
                    ActionRequest(
                        action="fs.write",
                        target=str(ws / f"file_{i:04d}.txt"),
                        params={"content": f"content for file {i}\n" * 10},
                    )
                )
                latencies.append((time.monotonic() - t0) * 1000)
                if result.status != "OK":
                    errors += 1
            duration = time.monotonic() - start

        return PerfResult(
            name=f"Write throughput ({n_ops} files)",
            total_ops=n_ops,
            duration_s=duration,
            latencies_ms=latencies,
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("\n" + "=" * 60)
    print("  Agent OS Kernel — Performance & Load Tests")
    print("=" * 60)

    results = []

    print("\n[1/6] Sequential throughput (deny-only)...")
    results.append(test_sequential_throughput(n_ops=2000))

    print("[2/6] Sequential throughput (fs.read with provider)...")
    results.append(test_sequential_with_provider(n_ops=500))

    print("[3/6] Concurrent load (10 threads × 100 ops)...")
    results.append(test_concurrent_load(n_threads=10, ops_per_thread=100))

    print("[4/6] Log integrity under concurrent load...")
    integrity = test_log_integrity_concurrent(n_threads=8, ops_per_thread=50)
    print(
        f"      Expected: {integrity['expected_entries']}, "
        f"Actual: {integrity['actual_entries']}, "
        f"OK: {integrity['integrity_ok']}"
    )
    if not integrity["integrity_ok"]:
        print("      ⚠ LOG INTEGRITY FAILURE — entries dropped or duplicated!")
    else:
        print("      ✅ Log integrity verified")

    print("[5/6] Mixed allow/deny stress (1000 ops)...")
    results.append(test_mixed_stress(n_ops=1000))

    print("[6/6] Write throughput (200 files)...")
    results.append(test_write_throughput(n_ops=200))

    # Print all results
    for r in results:
        r.print()

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    for r in results:
        status = "✅" if r.errors == 0 else f"⚠ ({r.errors} errors)"
        print(f"  {r.name[:45]:45s} {r.ops_per_sec:6.0f} ops/s  p99={r.p99:.1f}ms  {status}")
    if integrity["integrity_ok"]:
        print(f"  {'Log integrity (concurrent)':45s} ✅ {integrity['actual_entries']} entries verified")
    else:
        print(f"  {'Log integrity (concurrent)':45s} ⚠ FAILED")
    print()


if __name__ == "__main__":
    main()
