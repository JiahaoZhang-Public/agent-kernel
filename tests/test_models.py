"""Tests for the core object model (ActionRequest, ActionResult, Record)."""

from __future__ import annotations

from agent_os_kernel.models import ActionRequest, ActionResult, Record


class TestActionRequest:
    """Tests for ActionRequest dataclass."""

    def test_valid_request(self):
        req = ActionRequest(action="fs.read", target="/workspace/data.csv")
        assert req.validate() is True

    def test_valid_request_with_params(self):
        req = ActionRequest(action="fs.write", target="/workspace/out.txt", params={"content": "hello"})
        assert req.validate() is True
        assert req.params == {"content": "hello"}

    def test_empty_action_is_invalid(self):
        req = ActionRequest(action="", target="/workspace/data.csv")
        assert req.validate() is False

    def test_empty_target_is_invalid(self):
        req = ActionRequest(action="fs.read", target="")
        assert req.validate() is False

    def test_both_empty_is_invalid(self):
        req = ActionRequest(action="", target="")
        assert req.validate() is False

    def test_default_params_is_empty_dict(self):
        req = ActionRequest(action="fs.read", target="/workspace/data.csv")
        assert req.params == {}

    def test_params_independence(self):
        """Ensure default_factory creates independent dicts for each instance."""
        req1 = ActionRequest(action="fs.read", target="/a")
        req2 = ActionRequest(action="fs.read", target="/b")
        req1.params["key"] = "value"
        assert "key" not in req2.params


class TestActionResult:
    """Tests for ActionResult dataclass."""

    def test_ok_result(self):
        result = ActionResult(status="OK", data={"bytes_written": 5})
        assert result.status == "OK"
        assert result.data == {"bytes_written": 5}
        assert result.error is None
        assert result.record_id is None

    def test_denied_result(self):
        result = ActionResult(status="DENIED", error="not permitted")
        assert result.status == "DENIED"
        assert result.data is None
        assert result.error == "not permitted"

    def test_error_result(self):
        result = ActionResult(status="ERROR", error="something broke")
        assert result.status == "ERROR"

    def test_result_with_record_id(self):
        result = ActionResult(status="OK", data="content", record_id="abc123")
        assert result.record_id == "abc123"


class TestRecord:
    """Tests for Record dataclass."""

    def test_minimal_record(self):
        record = Record(
            timestamp="2026-01-01T00:00:00+00:00",
            action="fs.read",
            target="/workspace/data.csv",
            status="OK",
        )
        assert record.timestamp == "2026-01-01T00:00:00+00:00"
        assert record.action == "fs.read"
        assert record.target == "/workspace/data.csv"
        assert record.status == "OK"
        assert record.error is None
        assert record.duration_ms is None
        assert record.record_id is None

    def test_full_record(self):
        record = Record(
            timestamp="2026-01-01T00:00:00+00:00",
            action="fs.write",
            target="/workspace/out.txt",
            status="OK",
            error=None,
            duration_ms=42,
            record_id="snap-001",
        )
        assert record.duration_ms == 42
        assert record.record_id == "snap-001"

    def test_failed_record(self):
        record = Record(
            timestamp="2026-01-01T00:00:00+00:00",
            action="net.http",
            target="https://example.com",
            status="FAILED",
            error="connection timeout",
            duration_ms=5000,
        )
        assert record.status == "FAILED"
        assert record.error == "connection timeout"
