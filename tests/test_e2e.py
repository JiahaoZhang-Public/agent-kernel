"""End-to-end integration tests for the Agent OS Kernel.

These tests exercise the full workflow: policy + kernel + providers + log + reversible layer.
"""

from __future__ import annotations

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.log import Log
from agent_os_kernel.models import ActionRequest
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.http import HttpProvider
from agent_os_kernel.providers.process import ProcessProvider
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)


class TestFullKernelWorkflow:
    """Test complete kernel lifecycle: init, submit, log, close."""

    def test_filesystem_read_write_delete_cycle(self, tmp_path):
        """Full CRUD cycle through the kernel."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
                CapabilityRule(action="fs.write", resource=f"{ws}/**"),
                CapabilityRule(action="fs.delete", resource=f"{ws}/**"),
            ]
        )

        log_path = tmp_path / "kernel.log"
        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as k:
            # Write
            result = k.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(ws / "test.txt"),
                    params={"content": "hello world"},
                )
            )
            assert result.status == "OK"
            assert result.data == {"bytes_written": 11}

            # Read
            result = k.submit(ActionRequest(action="fs.read", target=str(ws / "test.txt")))
            assert result.status == "OK"
            assert result.data == "hello world"

            # Delete
            result = k.submit(ActionRequest(action="fs.delete", target=str(ws / "test.txt")))
            assert result.status == "OK"
            assert result.data == {"deleted": True}

            # Read after delete — should fail
            result = k.submit(ActionRequest(action="fs.read", target=str(ws / "test.txt")))
            assert result.status == "ERROR"
            assert "not found" in result.error.lower()

        # Verify all 4 actions are in the log
        records = Log(log_path).read_all()
        assert len(records) == 4
        assert [r.status for r in records] == ["OK", "OK", "OK", "FAILED"]

    def test_policy_enforcement_across_providers(self, tmp_path):
        """Test that policy blocks actions across different providers."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
                CapabilityRule(action="proc.exec", resource="echo"),
            ]
        )

        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=policy,
            providers=[FilesystemProvider(), ProcessProvider()],
            log_path=log_path,
        ) as k:
            # Allowed: fs.read in workspace
            (ws / "data.txt").write_text("ok")
            result = k.submit(ActionRequest(action="fs.read", target=str(ws / "data.txt")))
            assert result.status == "OK"

            # Denied: fs.write (not in policy)
            result = k.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(ws / "new.txt"),
                    params={"content": "x"},
                )
            )
            assert result.status == "DENIED"

            # Allowed: proc.exec echo
            result = k.submit(
                ActionRequest(
                    action="proc.exec",
                    target="echo",
                    params={"args": ["test"]},
                )
            )
            assert result.status == "OK"
            assert "test" in result.data["stdout"]

            # Denied: proc.exec rm (not in policy)
            result = k.submit(ActionRequest(action="proc.exec", target="rm", params={"args": ["-rf", "/"]}))
            assert result.status == "DENIED"

        # Verify log completeness
        records = Log(log_path).read_all()
        assert len(records) == 4
        statuses = [r.status for r in records]
        assert statuses.count("OK") == 2
        assert statuses.count("DENIED") == 2

    def test_yaml_policy_integration(self, tmp_path):
        """Test kernel with YAML policy file from configs/."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(f"""capabilities:
  - action: fs.read
    resource: {ws}/**
  - action: proc.exec
    resource: echo
""")

        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=str(policy_file),
            providers=[FilesystemProvider(), ProcessProvider()],
            log_path=log_path,
        ) as k:
            (ws / "hello.txt").write_text("hi")
            result = k.submit(ActionRequest(action="fs.read", target=str(ws / "hello.txt")))
            assert result.status == "OK"
            assert result.data == "hi"


class TestReversibleLayerE2E:
    """End-to-end tests for the reversible action layer."""

    def test_write_and_rollback_restores_content(self, tmp_path):
        """Write a file, then rollback should restore original content."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        target_file = ws / "doc.txt"
        target_file.write_text("original text")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
                CapabilityRule(action="fs.write", resource=f"{ws}/**"),
            ]
        )

        log_path = tmp_path / "kernel.log"
        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as k:
            store = SnapshotStore(str(tmp_path / ".snapshots"))
            layer = ReversibleActionLayer(
                kernel=k,
                strategies=[FsWriteSnapshotStrategy()],
                store=store,
            )

            # Write new content
            result = layer.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(target_file),
                    params={"content": "modified by agent"},
                )
            )
            assert result.status == "OK"
            assert result.record_id is not None
            assert target_file.read_text() == "modified by agent"

            # Rollback
            rollback_result = layer.rollback(result.record_id)
            assert rollback_result.status == "OK"
            assert target_file.read_text() == "original text"

        # Log should contain: write + rollback write
        records = Log(log_path).read_all()
        assert len(records) == 2
        assert all(r.status == "OK" for r in records)

    def test_write_new_file_and_rollback_deletes_it(self, tmp_path):
        """Writing a new file and rolling back should delete it."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        target_file = ws / "new_file.txt"
        assert not target_file.exists()

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.write", resource=f"{ws}/**"),
                CapabilityRule(action="fs.delete", resource=f"{ws}/**"),
            ]
        )

        log_path = tmp_path / "kernel.log"
        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as k:
            store = SnapshotStore(str(tmp_path / ".snapshots"))
            layer = ReversibleActionLayer(
                kernel=k,
                strategies=[FsWriteSnapshotStrategy()],
                store=store,
            )

            # Write new file
            result = layer.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(target_file),
                    params={"content": "should not persist"},
                )
            )
            assert result.status == "OK"
            assert target_file.exists()

            # Rollback should delete the file
            rollback_result = layer.rollback(result.record_id)
            assert rollback_result.status == "OK"
            assert not target_file.exists()

    def test_non_reversible_action_has_no_record_id(self, tmp_path):
        """Actions without a snapshot strategy should not get a record_id."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "data.txt").write_text("hello")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
            ]
        )

        log_path = tmp_path / "kernel.log"
        with Kernel(policy=policy, providers=[FilesystemProvider()], log_path=log_path) as k:
            store = SnapshotStore(str(tmp_path / ".snapshots"))
            layer = ReversibleActionLayer(
                kernel=k,
                strategies=[FsWriteSnapshotStrategy()],
                store=store,
            )

            result = layer.submit(ActionRequest(action="fs.read", target=str(ws / "data.txt")))
            assert result.status == "OK"
            assert result.record_id is None


class TestMultiProviderE2E:
    """Test kernel with all providers registered."""

    def test_all_builtin_providers(self, tmp_path):
        """Verify all built-in providers work together."""
        ws = tmp_path / "workspace"
        ws.mkdir()

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
                CapabilityRule(action="fs.write", resource=f"{ws}/**"),
                CapabilityRule(action="proc.exec", resource="echo"),
            ]
        )

        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=policy,
            providers=[FilesystemProvider(), ProcessProvider(), HttpProvider()],
            log_path=log_path,
        ) as k:
            # fs.write
            result = k.submit(
                ActionRequest(
                    action="fs.write",
                    target=str(ws / "out.txt"),
                    params={"content": "hello"},
                )
            )
            assert result.status == "OK"

            # fs.read
            result = k.submit(ActionRequest(action="fs.read", target=str(ws / "out.txt")))
            assert result.status == "OK"
            assert result.data == "hello"

            # proc.exec
            result = k.submit(
                ActionRequest(
                    action="proc.exec",
                    target="echo",
                    params={"args": ["world"]},
                )
            )
            assert result.status == "OK"
            assert "world" in result.data["stdout"]

            # net.http — denied (not in policy)
            result = k.submit(
                ActionRequest(
                    action="net.http",
                    target="https://example.com",
                )
            )
            assert result.status == "DENIED"


class TestLogIntegrity:
    """Verify log invariants across complex workflows."""

    def test_every_submit_produces_one_record(self, tmp_path):
        """Fundamental invariant: every submit() = exactly one log entry."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "file.txt").write_text("data")

        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource=f"{ws}/**"),
                CapabilityRule(action="fs.write", resource=f"{ws}/**"),
                CapabilityRule(action="proc.exec", resource="echo"),
            ]
        )

        log_path = tmp_path / "kernel.log"
        n_submits = 0
        with Kernel(
            policy=policy,
            providers=[FilesystemProvider(), ProcessProvider()],
            log_path=log_path,
        ) as k:
            # Various submits
            k.submit(ActionRequest(action="", target=""))  # INVALID
            n_submits += 1
            k.submit(ActionRequest(action="fs.write", target="/etc/x", params={"content": "x"}))  # DENIED
            n_submits += 1
            k.submit(ActionRequest(action="fs.read", target=str(ws / "file.txt")))  # OK
            n_submits += 1
            k.submit(ActionRequest(action="proc.exec", target="echo", params={"args": ["hi"]}))  # OK
            n_submits += 1
            k.submit(ActionRequest(action="unknown.action", target="x"))  # DENIED
            n_submits += 1

        records = Log(log_path).read_all()
        assert len(records) == n_submits

    def test_log_timestamps_are_ordered(self, tmp_path):
        """Log entries should be chronologically ordered."""
        policy = Policy(capabilities=[CapabilityRule(action="proc.exec", resource="echo")])
        log_path = tmp_path / "kernel.log"

        with Kernel(policy=policy, providers=[ProcessProvider()], log_path=log_path) as k:
            for _ in range(5):
                k.submit(ActionRequest(action="proc.exec", target="echo", params={"args": ["x"]}))

        records = Log(log_path).read_all()
        timestamps = [r.timestamp for r in records]
        assert timestamps == sorted(timestamps)
