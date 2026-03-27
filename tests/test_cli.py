"""Tests for the CLI entry point (__main__.py)."""

from __future__ import annotations

import json

from agent_os_kernel.__main__ import main


class TestCliVersion:
    def test_version_command(self, capsys):
        ret = main(["version"])
        assert ret == 0
        output = capsys.readouterr().out
        assert "agent-os-kernel" in output


class TestCliValidatePolicy:
    def test_valid_policy(self, tmp_path, capsys):
        policy = tmp_path / "policy.yaml"
        policy.write_text("capabilities:\n  - action: fs.read\n    resource: '**'\n")
        ret = main(["validate-policy", "--policy", str(policy)])
        assert ret == 0
        output = capsys.readouterr().out
        assert "1 capability rules" in output

    def test_invalid_policy(self, tmp_path, capsys):
        policy = tmp_path / "bad.yaml"
        policy.write_text("not: valid: yaml: [")
        ret = main(["validate-policy", "--policy", str(policy)])
        assert ret == 1

    def test_missing_policy(self, capsys):
        ret = main(["validate-policy", "--policy", "/nonexistent/policy.yaml"])
        assert ret == 1


class TestCliSubmit:
    def test_submit_allowed_action(self, tmp_path, capsys):
        # Create a file to read
        data_file = tmp_path / "data.txt"
        data_file.write_text("hello")

        policy = tmp_path / "policy.yaml"
        policy.write_text(f"capabilities:\n  - action: fs.read\n    resource: {tmp_path}/**\n")

        log_path = tmp_path / "kernel.log"
        ret = main(
            [
                "submit",
                "--policy",
                str(policy),
                "--action",
                "fs.read",
                "--target",
                str(data_file),
                "--log-path",
                str(log_path),
            ]
        )
        assert ret == 0
        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "OK"
        assert output["data"] == "hello"

    def test_submit_denied_action(self, tmp_path, capsys):
        policy = tmp_path / "policy.yaml"
        policy.write_text("capabilities:\n  - action: fs.read\n    resource: /workspace/**\n")

        log_path = tmp_path / "kernel.log"
        ret = main(
            [
                "submit",
                "--policy",
                str(policy),
                "--action",
                "fs.write",
                "--target",
                "/etc/passwd",
                "--log-path",
                str(log_path),
            ]
        )
        assert ret == 1
        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "DENIED"

    def test_submit_with_params(self, tmp_path, capsys):
        target = tmp_path / "output.txt"
        policy = tmp_path / "policy.yaml"
        policy.write_text(f"capabilities:\n  - action: fs.write\n    resource: {tmp_path}/**\n")

        log_path = tmp_path / "kernel.log"
        ret = main(
            [
                "submit",
                "--policy",
                str(policy),
                "--action",
                "fs.write",
                "--target",
                str(target),
                "--params",
                '{"content": "written by CLI"}',
                "--log-path",
                str(log_path),
            ]
        )
        assert ret == 0
        assert target.read_text() == "written by CLI"


class TestCliLog:
    def test_log_display(self, tmp_path, capsys):
        # Create a kernel log by submitting actions
        policy = tmp_path / "policy.yaml"
        policy.write_text(f"capabilities:\n  - action: fs.read\n    resource: {tmp_path}/**\n")

        log_path = tmp_path / "kernel.log"
        # Submit an action to create a log entry
        data = tmp_path / "x.txt"
        data.write_text("x")
        main(
            [
                "submit",
                "--policy",
                str(policy),
                "--action",
                "fs.read",
                "--target",
                str(data),
                "--log-path",
                str(log_path),
            ]
        )
        capsys.readouterr()  # clear

        ret = main(["log", "--log-path", str(log_path)])
        assert ret == 0
        output = capsys.readouterr().out
        entries = [json.loads(line) for line in output.strip().split("\n")]
        assert len(entries) == 1
        assert entries[0]["status"] == "OK"

    def test_log_filter_by_status(self, tmp_path, capsys):
        policy = tmp_path / "policy.yaml"
        policy.write_text(f"capabilities:\n  - action: fs.read\n    resource: {tmp_path}/**\n")

        log_path = tmp_path / "kernel.log"
        data = tmp_path / "x.txt"
        data.write_text("x")
        main(
            [
                "submit",
                "--policy",
                str(policy),
                "--action",
                "fs.read",
                "--target",
                str(data),
                "--log-path",
                str(log_path),
            ]
        )
        # Also submit a denied action
        main(
            [
                "submit",
                "--policy",
                str(policy),
                "--action",
                "fs.write",
                "--target",
                "/etc/x",
                "--log-path",
                str(log_path),
            ]
        )
        capsys.readouterr()  # clear

        ret = main(["log", "--log-path", str(log_path), "--status", "DENIED"])
        assert ret == 0
        output = capsys.readouterr().out
        entries = [json.loads(line) for line in output.strip().split("\n")]
        assert all(e["status"] == "DENIED" for e in entries)

    def test_log_missing_file(self, capsys):
        ret = main(["log", "--log-path", "/nonexistent/kernel.log"])
        assert ret == 1

    def test_log_limit(self, tmp_path, capsys):
        policy = tmp_path / "policy.yaml"
        policy.write_text(f"capabilities:\n  - action: fs.read\n    resource: {tmp_path}/**\n")

        log_path = tmp_path / "kernel.log"
        data = tmp_path / "x.txt"
        data.write_text("x")
        for _ in range(5):
            main(
                [
                    "submit",
                    "--policy",
                    str(policy),
                    "--action",
                    "fs.read",
                    "--target",
                    str(data),
                    "--log-path",
                    str(log_path),
                ]
            )
        capsys.readouterr()

        ret = main(["log", "--log-path", str(log_path), "--limit", "2"])
        assert ret == 0
        output = capsys.readouterr().out
        entries = [json.loads(line) for line in output.strip().split("\n")]
        assert len(entries) == 2


class TestCliNoCommand:
    def test_no_command_prints_help(self, capsys):
        ret = main([])
        assert ret == 0
