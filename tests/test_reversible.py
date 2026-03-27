"""Tests for the Reversible Action Layer (v2.1).

Covers FsWriteSnapshotStrategy, SnapshotStore, and ReversibleActionLayer.
"""

from __future__ import annotations

import json
import time

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)

# ---------------------------------------------------------------------------
# FsWriteSnapshotStrategy
# ---------------------------------------------------------------------------


class TestFsWriteSnapshotStrategy:
    """Tests for FsWriteSnapshotStrategy."""

    def test_supports_fs_write(self):
        strategy = FsWriteSnapshotStrategy()
        assert strategy.supports(ActionRequest(action="fs.write", target="/tmp/x")) is True

    def test_does_not_support_other_actions(self):
        strategy = FsWriteSnapshotStrategy()
        assert strategy.supports(ActionRequest(action="fs.read", target="/tmp/x")) is False
        assert strategy.supports(ActionRequest(action="fs.delete", target="/tmp/x")) is False

    def test_capture_existing_file(self, tmp_path):
        f = tmp_path / "existing.txt"
        f.write_text("original content")
        strategy = FsWriteSnapshotStrategy()
        snapshot = strategy.capture(ActionRequest(action="fs.write", target=str(f)))
        assert snapshot["existed"] is True
        assert snapshot["content"] == "original content"

    def test_capture_nonexistent_file(self, tmp_path):
        strategy = FsWriteSnapshotStrategy()
        snapshot = strategy.capture(ActionRequest(action="fs.write", target=str(tmp_path / "new.txt")))
        assert snapshot["existed"] is False
        assert "content" not in snapshot

    def test_restore_existing_file_produces_write(self, tmp_path):
        strategy = FsWriteSnapshotStrategy()
        snapshot = {"existed": True, "content": "original"}
        req = ActionRequest(action="fs.write", target=str(tmp_path / "x.txt"))
        restore_req = strategy.restore(req, snapshot)
        assert restore_req.action == "fs.write"
        assert restore_req.target == str(tmp_path / "x.txt")
        assert restore_req.params["content"] == "original"

    def test_restore_nonexistent_file_produces_delete(self, tmp_path):
        strategy = FsWriteSnapshotStrategy()
        snapshot = {"existed": False}
        req = ActionRequest(action="fs.write", target=str(tmp_path / "x.txt"))
        restore_req = strategy.restore(req, snapshot)
        assert restore_req.action == "fs.delete"
        assert restore_req.target == str(tmp_path / "x.txt")


# ---------------------------------------------------------------------------
# SnapshotStore
# ---------------------------------------------------------------------------


class TestSnapshotStore:
    """Tests for SnapshotStore persistence and TTL."""

    def test_save_and_load(self, tmp_path):
        store = SnapshotStore(tmp_path / "snapshots")
        req = ActionRequest(action="fs.write", target="/workspace/out.txt", params={"content": "hello"})
        snapshot = {"existed": True, "content": "old"}
        store.save("rec-001", req, snapshot)

        loaded = store.load("rec-001")
        assert loaded is not None
        loaded_req, loaded_snapshot = loaded
        assert loaded_req.action == "fs.write"
        assert loaded_req.target == "/workspace/out.txt"
        assert loaded_req.params == {"content": "hello"}
        assert loaded_snapshot == {"existed": True, "content": "old"}

    def test_load_nonexistent(self, tmp_path):
        store = SnapshotStore(tmp_path / "snapshots")
        assert store.load("nonexistent") is None

    def test_delete(self, tmp_path):
        store = SnapshotStore(tmp_path / "snapshots")
        req = ActionRequest(action="fs.write", target="/t")
        store.save("rec-002", req, {"existed": False})
        store.delete("rec-002")
        assert store.load("rec-002") is None

    def test_delete_nonexistent_does_not_raise(self, tmp_path):
        store = SnapshotStore(tmp_path / "snapshots")
        store.delete("nonexistent")  # Should not raise

    def test_ttl_expiry(self, tmp_path):
        """Expired snapshots should return None and be cleaned up."""
        store = SnapshotStore(tmp_path / "snapshots", ttl_seconds=1)
        req = ActionRequest(action="fs.write", target="/t")
        store.save("rec-ttl", req, {"existed": False})

        # Manually backdate the created_at timestamp
        snap_file = tmp_path / "snapshots" / "rec-ttl.json"
        entry = json.loads(snap_file.read_text())
        entry["created_at"] = time.time() - 100  # 100 seconds ago
        snap_file.write_text(json.dumps(entry))

        assert store.load("rec-ttl") is None
        # File should be deleted
        assert not snap_file.exists()

    def test_ttl_not_expired(self, tmp_path):
        store = SnapshotStore(tmp_path / "snapshots", ttl_seconds=3600)
        req = ActionRequest(action="fs.write", target="/t")
        store.save("rec-ok", req, {"existed": False})
        assert store.load("rec-ok") is not None

    def test_store_creates_directory(self, tmp_path):
        store_dir = tmp_path / "nested" / "store"
        SnapshotStore(store_dir)
        assert store_dir.exists()

    def test_snapshot_file_is_valid_json(self, tmp_path):
        store = SnapshotStore(tmp_path / "snapshots")
        req = ActionRequest(action="fs.write", target="/t", params={"content": "x"})
        store.save("rec-json", req, {"existed": True, "content": "x"})
        snap_file = tmp_path / "snapshots" / "rec-json.json"
        data = json.loads(snap_file.read_text())
        assert data["record_id"] == "rec-json"
        assert "created_at" in data


# ---------------------------------------------------------------------------
# ReversibleActionLayer
# ---------------------------------------------------------------------------


def _fs_policy() -> Policy:
    """Policy allowing fs.read, fs.write, fs.delete on any path."""
    return Policy(
        capabilities=[
            CapabilityRule(action="fs.read", resource="*"),
            CapabilityRule(action="fs.write", resource="*"),
            CapabilityRule(action="fs.delete", resource="*"),
        ]
    )


class TestReversibleActionLayer:
    """Tests for the ReversibleActionLayer orchestration."""

    def test_submit_creates_snapshot_for_write(self, tmp_path):
        """Writing a new file should produce a snapshot with record_id."""
        log_path = tmp_path / "kernel.log"
        target = tmp_path / "new_file.txt"

        with Kernel(
            policy=_fs_policy(),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)

            result = layer.submit(ActionRequest(action="fs.write", target=str(target), params={"content": "hello"}))

        assert result.status == "OK"
        assert result.record_id is not None
        assert target.read_text() == "hello"

    def test_submit_non_reversible_action_has_no_record_id(self, tmp_path):
        """A read action should pass through without creating a snapshot."""
        log_path = tmp_path / "kernel.log"
        target = tmp_path / "data.txt"
        target.write_text("content")

        with Kernel(
            policy=_fs_policy(),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)

            result = layer.submit(ActionRequest(action="fs.read", target=str(target)))

        assert result.status == "OK"
        assert result.record_id is None

    def test_rollback_restores_original_content(self, tmp_path):
        """Overwriting a file and rolling back should restore original content."""
        log_path = tmp_path / "kernel.log"
        target = tmp_path / "file.txt"
        target.write_text("original")

        with Kernel(
            policy=_fs_policy(),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)

            # Overwrite the file
            result = layer.submit(
                ActionRequest(action="fs.write", target=str(target), params={"content": "overwritten"})
            )
            assert target.read_text() == "overwritten"
            record_id = result.record_id

            # Roll back
            rollback_result = layer.rollback(record_id)
            assert rollback_result.status == "OK"
            assert target.read_text() == "original"

    def test_rollback_deletes_newly_created_file(self, tmp_path):
        """Writing a new file and rolling back should delete it."""
        log_path = tmp_path / "kernel.log"
        target = tmp_path / "new.txt"

        with Kernel(
            policy=_fs_policy(),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)

            result = layer.submit(
                ActionRequest(action="fs.write", target=str(target), params={"content": "new content"})
            )
            assert target.exists()
            record_id = result.record_id

            rollback_result = layer.rollback(record_id)
            assert rollback_result.status == "OK"
            assert not target.exists()

    def test_rollback_nonexistent_snapshot(self, tmp_path):
        """Rolling back with an invalid record_id returns an error."""
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=_fs_policy(),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)
            result = layer.rollback("nonexistent-id")
        assert result.status == "ERROR"
        assert "no snapshot" in result.error

    def test_rollback_cleans_up_snapshot(self, tmp_path):
        """After a successful rollback, the snapshot should be deleted."""
        log_path = tmp_path / "kernel.log"
        target = tmp_path / "file.txt"
        target.write_text("original")

        with Kernel(
            policy=_fs_policy(),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)

            result = layer.submit(ActionRequest(action="fs.write", target=str(target), params={"content": "new"}))
            record_id = result.record_id
            layer.rollback(record_id)

            # Snapshot should be gone — second rollback fails
            second = layer.rollback(record_id)
            assert second.status == "ERROR"
            assert "no snapshot" in second.error

    def test_submit_denied_action_no_snapshot(self, tmp_path):
        """If the kernel denies the action, no snapshot should be created."""
        log_path = tmp_path / "kernel.log"
        empty_policy = Policy(capabilities=[])

        with Kernel(
            policy=empty_policy,
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)

            result = layer.submit(
                ActionRequest(action="fs.write", target=str(tmp_path / "x.txt"), params={"content": "x"})
            )

        assert result.status == "DENIED"
        assert result.record_id is None

    def test_multiple_writes_independent_rollbacks(self, tmp_path):
        """Multiple writes create independent snapshots, each rollback-able."""
        log_path = tmp_path / "kernel.log"
        file_a = tmp_path / "a.txt"
        file_b = tmp_path / "b.txt"
        file_a.write_text("orig_a")
        file_b.write_text("orig_b")

        with Kernel(
            policy=_fs_policy(),
            providers=[FilesystemProvider()],
            log_path=log_path,
        ) as k:
            store = SnapshotStore(tmp_path / "snapshots")
            layer = ReversibleActionLayer(k, [FsWriteSnapshotStrategy()], store)

            r1 = layer.submit(ActionRequest(action="fs.write", target=str(file_a), params={"content": "new_a"}))
            r2 = layer.submit(ActionRequest(action="fs.write", target=str(file_b), params={"content": "new_b"}))

            # Roll back only file_a
            layer.rollback(r1.record_id)
            assert file_a.read_text() == "orig_a"
            assert file_b.read_text() == "new_b"

            # Roll back file_b
            layer.rollback(r2.record_id)
            assert file_b.read_text() == "orig_b"
