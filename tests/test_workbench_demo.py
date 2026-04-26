"""Tests for the interactive Workbench demo runtime."""

from __future__ import annotations

import asyncio

from demo.backend.runtime import (
    DEFAULT_POLICY_YAML,
    DemoWorld,
    deterministic_step,
    kernel_submit,
    stream_scenario,
)

from agent_os_kernel.models import ActionRequest


def test_dangerous_db_action_is_denied_and_logged(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    world = DemoWorld()
    request = ActionRequest(action="db.write", target="prod/users", params={"sql": "DROP TABLE users;"})

    result, record = kernel_submit(world=world, policy_yaml=DEFAULT_POLICY_YAML, log_path=log_path, request=request)

    assert result.status == "DENIED"
    assert record is not None
    assert record["status"] == "DENIED"
    assert world.tables["prod/users"]["dropped"] is False


def test_safe_test_table_write_is_allowed(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    world = DemoWorld()
    request = ActionRequest(
        action="db.write",
        target="prod/test_sessions",
        params={"sql": "DELETE FROM prod.test_sessions WHERE fixture = true;"},
    )

    result, record = kernel_submit(world=world, policy_yaml=DEFAULT_POLICY_YAML, log_path=log_path, request=request)

    assert result.status == "OK"
    assert result.data["rowsAffected"] == 2
    assert record is not None
    assert record["status"] == "OK"
    assert world.tables["prod/test_sessions"]["rows"] == []


def test_llm_fallback_step_repairs_denied_action():
    first = deterministic_step("dangerous-db")
    observation = {
        "request": {"action": first["action"], "target": first["target"], "params": first["params"]},
        "result": {"status": "DENIED", "error": "not permitted"},
    }

    repaired = deterministic_step("dangerous-db", observation)

    assert first["target"] == "prod/users"
    assert repaired["target"] == "prod/test_sessions"


def test_llm_mode_stream_exposes_prompt_tool_output_and_log(tmp_path):
    async def collect() -> list[dict[str, object]]:
        return [
            event
            async for event in stream_scenario(
                scenario="dangerous-db",
                prompt="Clean up test data from the database",
                mode="llm",
                policy_yaml=DEFAULT_POLICY_YAML,
                log_path=tmp_path / "audit.jsonl",
            )
        ]

    events = asyncio.run(collect())
    titles = [str(event["title"]) for event in events]

    assert "User prompt" in titles
    assert "LLM output: first agent step" in titles
    assert "Agent tool call: kernel.submit" in titles
    assert "Tool output / Kernel observation: DENIED" in titles
    assert "Tool output / Kernel observation: OK" in titles
