"""Tests for the Policy engine (YAML loading, glob matching, default deny)."""

from __future__ import annotations

import pytest

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.policy import CapabilityRule, Policy, load_policy

# ---------------------------------------------------------------------------
# CapabilityRule unit tests
# ---------------------------------------------------------------------------


class TestCapabilityRule:
    """Tests for individual CapabilityRule matching."""

    def test_action_matches_exact(self):
        rule = CapabilityRule(action="fs.read", resource="/workspace/**")
        assert rule.action_matches("fs.read") is True
        assert rule.action_matches("fs.write") is False

    def test_resource_matches_glob(self):
        rule = CapabilityRule(action="fs.read", resource="/workspace/**")
        assert rule.resource_matches("/workspace/data.csv") is True
        assert rule.resource_matches("/workspace/sub/deep/file.txt") is True
        assert rule.resource_matches("/etc/passwd") is False

    def test_resource_matches_exact(self):
        rule = CapabilityRule(action="proc.exec", resource="git")
        assert rule.resource_matches("git") is True
        assert rule.resource_matches("rm") is False

    def test_constraint_matches_no_constraint(self):
        rule = CapabilityRule(action="fs.read", resource="/workspace/**")
        req = ActionRequest(action="fs.read", target="/workspace/data.csv")
        assert rule.constraint_matches(req) is True

    def test_constraint_matches_with_matching_param(self):
        rule = CapabilityRule(action="net.http", resource="https://api.example.com/**", constraint={"method": "GET"})
        req = ActionRequest(action="net.http", target="https://api.example.com/data", params={"method": "GET"})
        assert rule.constraint_matches(req) is True

    def test_constraint_rejects_mismatched_param(self):
        rule = CapabilityRule(action="net.http", resource="https://api.example.com/**", constraint={"method": "GET"})
        req = ActionRequest(action="net.http", target="https://api.example.com/data", params={"method": "POST"})
        assert rule.constraint_matches(req) is False

    def test_constraint_rejects_missing_param(self):
        rule = CapabilityRule(action="net.http", resource="https://api.example.com/**", constraint={"method": "GET"})
        req = ActionRequest(action="net.http", target="https://api.example.com/data", params={})
        assert rule.constraint_matches(req) is False

    def test_constraint_multiple_keys(self):
        rule = CapabilityRule(action="net.http", resource="*", constraint={"method": "GET", "timeout": 30})
        req_ok = ActionRequest(action="net.http", target="http://x", params={"method": "GET", "timeout": 30})
        req_bad = ActionRequest(action="net.http", target="http://x", params={"method": "GET", "timeout": 60})
        assert rule.constraint_matches(req_ok) is True
        assert rule.constraint_matches(req_bad) is False


# ---------------------------------------------------------------------------
# Policy unit tests
# ---------------------------------------------------------------------------


class TestPolicy:
    """Tests for Policy allow-list behavior."""

    def test_default_deny_empty_policy(self):
        policy = Policy(capabilities=[])
        req = ActionRequest(action="fs.read", target="/workspace/data.csv")
        assert policy.is_allowed(req) is False

    def test_allows_matching_rule(self):
        policy = Policy(capabilities=[CapabilityRule(action="fs.read", resource="/workspace/**")])
        req = ActionRequest(action="fs.read", target="/workspace/data.csv")
        assert policy.is_allowed(req) is True

    def test_denies_non_matching_action(self):
        policy = Policy(capabilities=[CapabilityRule(action="fs.read", resource="/workspace/**")])
        req = ActionRequest(action="fs.write", target="/workspace/data.csv")
        assert policy.is_allowed(req) is False

    def test_denies_non_matching_resource(self):
        policy = Policy(capabilities=[CapabilityRule(action="fs.read", resource="/workspace/**")])
        req = ActionRequest(action="fs.read", target="/etc/passwd")
        assert policy.is_allowed(req) is False

    def test_denies_when_constraint_fails(self):
        rule = CapabilityRule(action="net.http", resource="https://api.example.com/**", constraint={"method": "GET"})
        policy = Policy(capabilities=[rule])
        req = ActionRequest(action="net.http", target="https://api.example.com/data", params={"method": "POST"})
        assert policy.is_allowed(req) is False

    def test_allows_when_constraint_passes(self):
        rule = CapabilityRule(action="net.http", resource="https://api.example.com/**", constraint={"method": "GET"})
        policy = Policy(capabilities=[rule])
        req = ActionRequest(action="net.http", target="https://api.example.com/data", params={"method": "GET"})
        assert policy.is_allowed(req) is True

    def test_multiple_rules_first_match_wins(self):
        policy = Policy(
            capabilities=[
                CapabilityRule(action="fs.read", resource="/workspace/**"),
                CapabilityRule(action="fs.write", resource="/workspace/output/**"),
            ]
        )
        assert policy.is_allowed(ActionRequest(action="fs.read", target="/workspace/foo")) is True
        assert policy.is_allowed(ActionRequest(action="fs.write", target="/workspace/output/bar")) is True
        assert policy.is_allowed(ActionRequest(action="fs.write", target="/workspace/foo")) is False


# ---------------------------------------------------------------------------
# load_policy tests
# ---------------------------------------------------------------------------


class TestLoadPolicy:
    """Tests for YAML policy loading."""

    def test_load_fixture_policy(self):
        """Load the test fixture and verify all rules are parsed."""
        policy = load_policy("tests/fixtures/test_policy.yaml")
        assert len(policy.capabilities) == 6

    def test_fixture_fs_read_allowed(self):
        policy = load_policy("tests/fixtures/test_policy.yaml")
        req = ActionRequest(action="fs.read", target="/workspace/data.csv")
        assert policy.is_allowed(req) is True

    def test_fixture_fs_write_outside_output_denied(self):
        policy = load_policy("tests/fixtures/test_policy.yaml")
        req = ActionRequest(action="fs.write", target="/workspace/data.csv")
        assert policy.is_allowed(req) is False

    def test_fixture_proc_exec_git_allowed(self):
        policy = load_policy("tests/fixtures/test_policy.yaml")
        req = ActionRequest(action="proc.exec", target="git")
        assert policy.is_allowed(req) is True

    def test_fixture_proc_exec_rm_denied(self):
        policy = load_policy("tests/fixtures/test_policy.yaml")
        req = ActionRequest(action="proc.exec", target="rm")
        assert policy.is_allowed(req) is False

    def test_fixture_net_http_get_allowed(self):
        policy = load_policy("tests/fixtures/test_policy.yaml")
        req = ActionRequest(action="net.http", target="https://api.example.com/data", params={"method": "GET"})
        assert policy.is_allowed(req) is True

    def test_fixture_net_http_post_denied(self):
        policy = load_policy("tests/fixtures/test_policy.yaml")
        req = ActionRequest(action="net.http", target="https://api.example.com/data", params={"method": "POST"})
        assert policy.is_allowed(req) is False

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_policy(tmp_path / "nonexistent.yaml")

    def test_load_malformed_no_capabilities_key(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("rules:\n  - action: fs.read\n    resource: /workspace/**\n")
        with pytest.raises(ValueError, match="capabilities"):
            load_policy(bad)

    def test_load_malformed_missing_action_key(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("capabilities:\n  - resource: /workspace/**\n")
        with pytest.raises(ValueError, match="action"):
            load_policy(bad)

    def test_load_malformed_missing_resource_key(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("capabilities:\n  - action: fs.read\n")
        with pytest.raises(ValueError, match="resource"):
            load_policy(bad)

    def test_load_empty_capabilities(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("capabilities: []\n")
        policy = load_policy(f)
        assert len(policy.capabilities) == 0

    def test_load_policy_with_constraint(self, tmp_path):
        f = tmp_path / "constrained.yaml"
        f.write_text(
            "capabilities:\n"
            "  - action: net.http\n"
            "    resource: https://api.example.com/**\n"
            "    constraint:\n"
            "      method: GET\n"
        )
        policy = load_policy(f)
        assert policy.capabilities[0].constraint == {"method": "GET"}

    def test_load_policy_accepts_path_object(self, tmp_path):
        f = tmp_path / "p.yaml"
        f.write_text("capabilities:\n  - action: fs.read\n    resource: /**\n")
        policy = load_policy(f)
        assert len(policy.capabilities) == 1
