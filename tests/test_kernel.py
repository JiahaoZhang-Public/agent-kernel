"""Integration tests for the Kernel (Gate) submit() flow.

Covers all 5 log statuses: INVALID, DENIED, NO_PROVIDER, FAILED, OK.
"""

from __future__ import annotations

from typing import Any

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.base import Provider

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class EchoProvider(Provider):
    """A trivial provider that echoes back the request params."""

    @property
    def actions(self) -> list[str]:
        return ["echo"]

    def execute(self, request: ActionRequest) -> Any:
        return {"echo": request.params}


class FailingProvider(Provider):
    """A provider that always raises."""

    @property
    def actions(self) -> list[str]:
        return ["fail"]

    def execute(self, request: ActionRequest) -> Any:
        raise RuntimeError("deliberate failure")


def _allow_all_policy() -> Policy:
    return Policy(capabilities=[CapabilityRule(action="*", resource="*")])


def _allow_echo_policy() -> Policy:
    return Policy(capabilities=[CapabilityRule(action="echo", resource="*")])


def _allow_fail_policy() -> Policy:
    return Policy(capabilities=[CapabilityRule(action="fail", resource="*")])


# ---------------------------------------------------------------------------
# Tests for each submit() path
# ---------------------------------------------------------------------------


class TestKernelSubmitPaths:
    """Exercise every code path through submit()."""

    def test_invalid_request(self, tmp_path):
        """Path 1: INVALID — malformed request."""
        log_path = tmp_path / "kernel.log"
        with Kernel(policy=_allow_echo_policy(), log_path=log_path) as k:
            result = k.submit(ActionRequest(action="", target=""))
        assert result.status == "ERROR"
        assert "malformed" in result.error

    def test_denied_request(self, tmp_path):
        """Path 2: DENIED — policy denies the request."""
        log_path = tmp_path / "kernel.log"
        policy = Policy(capabilities=[CapabilityRule(action="fs.read", resource="/workspace/**")])
        with Kernel(policy=policy, log_path=log_path) as k:
            result = k.submit(ActionRequest(action="fs.read", target="/etc/passwd"))
        assert result.status == "DENIED"
        assert "not permitted" in result.error

    def test_no_provider(self, tmp_path):
        """Path 3: NO_PROVIDER — action allowed but no provider registered."""
        log_path = tmp_path / "kernel.log"
        policy = Policy(capabilities=[CapabilityRule(action="echo", resource="*")])
        with Kernel(policy=policy, providers={}, log_path=log_path) as k:
            result = k.submit(ActionRequest(action="echo", target="x"))
        assert result.status == "ERROR"
        assert "no provider" in result.error

    def test_failed_execution(self, tmp_path):
        """Path 4: FAILED — provider raises an exception."""
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=_allow_fail_policy(),
            providers={"fail": FailingProvider()},
            log_path=log_path,
        ) as k:
            result = k.submit(ActionRequest(action="fail", target="anything"))
        assert result.status == "ERROR"
        assert "deliberate failure" in result.error

    def test_ok_execution(self, tmp_path):
        """Path 5: OK — happy path through the entire gate."""
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=_allow_echo_policy(),
            providers={"echo": EchoProvider()},
            log_path=log_path,
        ) as k:
            result = k.submit(ActionRequest(action="echo", target="hello", params={"msg": "world"}))
        assert result.status == "OK"
        assert result.data == {"echo": {"msg": "world"}}
        assert result.error is None


# ---------------------------------------------------------------------------
# Log record verification
# ---------------------------------------------------------------------------


class TestKernelLogRecords:
    """Verify that every submit() produces exactly one log record."""

    def test_every_path_logs_exactly_one_record(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        # Policy allows echo and noprov, but only echo has a provider
        policy = Policy(
            capabilities=[
                CapabilityRule(action="echo", resource="*"),
                CapabilityRule(action="noprov", resource="*"),
            ]
        )
        with Kernel(
            policy=policy,
            providers={"echo": EchoProvider()},
            log_path=log_path,
        ) as k:
            # INVALID
            k.submit(ActionRequest(action="", target=""))
            # DENIED (action not in policy)
            k.submit(ActionRequest(action="fs.read", target="/etc/passwd"))
            # NO_PROVIDER (allowed by policy but no provider registered)
            k.submit(ActionRequest(action="noprov", target="x"))
            # OK
            k.submit(ActionRequest(action="echo", target="t"))

        from agent_os_kernel.log import Log

        records = Log(log_path).read_all()
        assert len(records) == 4
        statuses = [r.status for r in records]
        assert "INVALID" in statuses
        assert "DENIED" in statuses
        assert "NO_PROVIDER" in statuses
        assert "OK" in statuses

    def test_ok_record_has_duration(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=_allow_echo_policy(),
            providers={"echo": EchoProvider()},
            log_path=log_path,
        ) as k:
            k.submit(ActionRequest(action="echo", target="t"))

        from agent_os_kernel.log import Log

        records = Log(log_path).read_all()
        assert records[0].status == "OK"
        assert records[0].duration_ms is not None
        assert records[0].duration_ms >= 0

    def test_failed_record_has_duration_and_error(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=_allow_fail_policy(),
            providers={"fail": FailingProvider()},
            log_path=log_path,
        ) as k:
            k.submit(ActionRequest(action="fail", target="t"))

        from agent_os_kernel.log import Log

        records = Log(log_path).read_all()
        assert records[0].status == "FAILED"
        assert records[0].duration_ms is not None
        assert records[0].error is not None


# ---------------------------------------------------------------------------
# Provider registration
# ---------------------------------------------------------------------------


class TestKernelProviderRegistration:
    """Test different ways to register providers."""

    def test_dict_registration(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=_allow_echo_policy(),
            providers={"echo": EchoProvider()},
            log_path=log_path,
        ) as k:
            result = k.submit(ActionRequest(action="echo", target="t"))
        assert result.status == "OK"

    def test_list_registration(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=_allow_echo_policy(),
            providers=[EchoProvider()],
            log_path=log_path,
        ) as k:
            result = k.submit(ActionRequest(action="echo", target="t"))
        assert result.status == "OK"

    def test_no_providers(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        with Kernel(policy=_allow_echo_policy(), log_path=log_path) as k:
            result = k.submit(ActionRequest(action="echo", target="t"))
        assert result.status == "ERROR"
        assert "no provider" in result.error


# ---------------------------------------------------------------------------
# Policy from YAML file
# ---------------------------------------------------------------------------


class TestKernelWithYAMLPolicy:
    """Test Kernel initialization with a YAML policy file."""

    def test_load_from_yaml_path(self, tmp_path):
        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text("capabilities:\n  - action: echo\n    resource: '*'\n")
        log_path = tmp_path / "kernel.log"
        with Kernel(
            policy=str(policy_file),
            providers={"echo": EchoProvider()},
            log_path=log_path,
        ) as k:
            result = k.submit(ActionRequest(action="echo", target="t"))
        assert result.status == "OK"

    def test_policy_property(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        p = _allow_echo_policy()
        with Kernel(policy=p, log_path=log_path) as k:
            assert k.policy is p

    def test_log_property(self, tmp_path):
        log_path = tmp_path / "kernel.log"
        with Kernel(policy=_allow_echo_policy(), log_path=log_path) as k:
            assert k.log is not None
