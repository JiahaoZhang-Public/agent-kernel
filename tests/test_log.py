"""Tests for the append-only JSONL Log."""

from __future__ import annotations

import json

import pytest

from agent_os_kernel.log import Log
from agent_os_kernel.models import Record


def _make_record(
    action: str = "fs.read",
    target: str = "/workspace/data.csv",
    status: str = "OK",
    **kwargs,
) -> Record:
    return Record(
        timestamp="2026-01-01T00:00:00+00:00",
        action=action,
        target=target,
        status=status,
        **kwargs,
    )


class TestLog:
    """Tests for Log JSONL writer/reader."""

    def test_write_and_read_single_record(self, tmp_path):
        log_path = tmp_path / "test.log"
        log = Log(log_path)
        log.open()
        record = _make_record()
        log.write(record)
        log.close()

        records = Log(log_path).read_all()
        assert len(records) == 1
        assert records[0].action == "fs.read"
        assert records[0].status == "OK"

    def test_write_multiple_records(self, tmp_path):
        log_path = tmp_path / "test.log"
        with Log(log_path) as log:
            log.write(_make_record(action="fs.read"))
            log.write(_make_record(action="fs.write", target="/workspace/output/out.txt"))
            log.write(_make_record(action="proc.exec", target="git", status="FAILED", error="timeout"))

        records = Log(log_path).read_all()
        assert len(records) == 3
        assert records[0].action == "fs.read"
        assert records[1].action == "fs.write"
        assert records[2].action == "proc.exec"
        assert records[2].error == "timeout"

    def test_append_only_behavior(self, tmp_path):
        """Opening and writing again appends, does not overwrite."""
        log_path = tmp_path / "test.log"
        with Log(log_path) as log:
            log.write(_make_record(action="fs.read"))

        with Log(log_path) as log:
            log.write(_make_record(action="fs.write"))

        records = Log(log_path).read_all()
        assert len(records) == 2

    def test_context_manager(self, tmp_path):
        log_path = tmp_path / "test.log"
        with Log(log_path) as log:
            log.write(_make_record())
        # File should be closed after exiting context
        assert log._file is None

    def test_write_without_open_raises(self, tmp_path):
        log_path = tmp_path / "test.log"
        log = Log(log_path)
        with pytest.raises(RuntimeError, match="not open"):
            log.write(_make_record())

    def test_read_all_nonexistent_file(self, tmp_path):
        log_path = tmp_path / "nonexistent.log"
        log = Log(log_path)
        assert log.read_all() == []

    def test_none_fields_are_omitted_in_json(self, tmp_path):
        """None values should not appear in the JSONL output."""
        log_path = tmp_path / "test.log"
        with Log(log_path) as log:
            log.write(_make_record())

        with log_path.open() as f:
            line = f.readline().strip()
            data = json.loads(line)
        assert "error" not in data
        assert "duration_ms" not in data
        assert "record_id" not in data

    def test_duration_ms_is_persisted(self, tmp_path):
        log_path = tmp_path / "test.log"
        with Log(log_path) as log:
            log.write(_make_record(duration_ms=42))

        records = Log(log_path).read_all()
        assert records[0].duration_ms == 42

    def test_record_id_is_persisted(self, tmp_path):
        log_path = tmp_path / "test.log"
        with Log(log_path) as log:
            log.write(_make_record(record_id="snap-001"))

        records = Log(log_path).read_all()
        assert records[0].record_id == "snap-001"

    def test_creates_parent_directories(self, tmp_path):
        log_path = tmp_path / "nested" / "dir" / "test.log"
        with Log(log_path) as log:
            log.write(_make_record())
        assert log_path.exists()

    def test_close_idempotent(self, tmp_path):
        log_path = tmp_path / "test.log"
        log = Log(log_path)
        log.open()
        log.close()
        log.close()  # Should not raise

    def test_each_record_is_one_line(self, tmp_path):
        log_path = tmp_path / "test.log"
        with Log(log_path) as log:
            for i in range(5):
                log.write(_make_record(target=f"/workspace/file{i}.txt"))

        lines = [line for line in log_path.read_text().splitlines() if line.strip()]
        assert len(lines) == 5
        for line in lines:
            json.loads(line)  # Each line must be valid JSON
