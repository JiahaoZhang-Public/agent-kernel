"""Runtime helpers for the Agent Kernel Workbench demo.

The demo intentionally uses the real ``agent_os_kernel`` package for policy
matching, Gate execution, and audit logging. The only mocked layer is the
external world touched by providers.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
import urllib.error
import urllib.request
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.log import Log
from agent_os_kernel.models import ActionRequest, ActionResult, Record
from agent_os_kernel.policy import CapabilityRule, Policy
from agent_os_kernel.providers.base import Provider
from agent_os_kernel.reversible import (
    ReversibleActionLayer,
    SnapshotStore,
    SnapshotStrategy,
)

DEFAULT_POLICY_YAML = """capabilities:
  - action: db.read
    resource: prod/**

  - action: db.write
    resource: prod/test_*

  - action: mcp.call
    resource: scholar/*

  - action: net.http
    resource: https://api.example.com/**
    constraint:
      method: GET
"""


SCENARIOS = [
    {
        "id": "dangerous-db",
        "title": "Dangerous DB Cleanup",
        "prompt": "Clean up test data from the database",
    },
    {
        "id": "mcp-scholar",
        "title": "MCP Scholar Search",
        "prompt": "Find recent kernel-mediated agent papers",
    },
    {
        "id": "http-egress",
        "title": "HTTP Egress Control",
        "prompt": "Send telemetry to the analysis endpoint",
    },
]


@dataclass
class LLMConfig:
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class DemoWorld:
    """In-memory fixtures that make provider effects visible in the UI."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.tables: dict[str, dict[str, Any]] = {
            "prod/users": {
                "dropped": False,
                "rows": [
                    {"id": 1, "email": "ada@example.com", "role": "admin"},
                    {"id": 2, "email": "grace@example.com", "role": "user"},
                    {"id": 3, "email": "linus@example.com", "role": "user"},
                ],
            },
            "prod/test_sessions": {
                "dropped": False,
                "rows": [
                    {"id": "sess_101", "user_id": 2, "fixture": True},
                    {"id": "sess_102", "user_id": 3, "fixture": True},
                ],
            },
            "prod/test_orders": {
                "dropped": False,
                "rows": [
                    {"id": "ord_test_1", "amount": 19},
                    {"id": "ord_test_2", "amount": 37},
                ],
            },
        }
        self.http_calls: list[dict[str, Any]] = []
        self.mcp_calls: list[dict[str, Any]] = []

    def snapshot(self) -> dict[str, Any]:
        return {
            "tables": copy.deepcopy(self.tables),
            "httpCalls": copy.deepcopy(self.http_calls),
            "mcpCalls": copy.deepcopy(self.mcp_calls),
        }


class DemoDatabaseProvider(Provider):
    def __init__(self, world: DemoWorld) -> None:
        self.world = world

    @property
    def actions(self) -> list[str]:
        return ["db.read", "db.write"]

    def execute(self, request: ActionRequest) -> Any:
        table = self.world.tables.setdefault(request.target, {"dropped": False, "rows": []})
        if request.action == "db.read":
            return {"table": request.target, "rows": copy.deepcopy(table["rows"]), "dropped": table["dropped"]}

        # Reversible-rollback restore branch — short-circuits before SQL parsing
        # so the rollback layer can deterministically reinstate prior rows.
        if request.params.get("__restore__"):
            rows = request.params.get("rows", [])
            dropped = bool(request.params.get("dropped", False))
            table["rows"] = copy.deepcopy(rows)
            table["dropped"] = dropped
            return {
                "operation": "RESTORE",
                "table": request.target,
                "rowsAffected": len(rows),
                "dropped": dropped,
            }

        sql = str(request.params.get("sql", "")).upper()
        if "DROP TABLE" in sql:
            rows_affected = len(table["rows"])
            table["rows"] = []
            table["dropped"] = True
            return {
                "operation": "DROP_TABLE",
                "table": request.target,
                "rowsAffected": rows_affected,
                "dropped": True,
            }

        if "DELETE" in sql:
            rows_affected = len(table["rows"])
            table["rows"] = []
            return {
                "operation": "DELETE",
                "table": request.target,
                "rowsAffected": rows_affected,
                "dropped": False,
            }

        return {"operation": "WRITE", "table": request.target, "rowsAffected": 0, "dropped": table["dropped"]}


class DemoMcpProvider(Provider):
    def __init__(self, world: DemoWorld) -> None:
        self.world = world

    @property
    def actions(self) -> list[str]:
        return ["mcp.call"]

    def execute(self, request: ActionRequest) -> Any:
        query = str(request.params.get("query") or request.params.get("arguments", {}).get("query") or "agent kernel")
        call = {"target": request.target, "query": query}
        self.world.mcp_calls.append(call)
        return {
            "tool": request.target,
            "papers": [
                {
                    "title": "Kernel-Mediated Tool Use for Language Agents",
                    "year": 2026,
                    "score": 0.93,
                },
                {
                    "title": "Policy Gates for Autonomous Software Agents",
                    "year": 2025,
                    "score": 0.88,
                },
            ],
        }


class DemoHttpProvider(Provider):
    def __init__(self, world: DemoWorld) -> None:
        self.world = world

    @property
    def actions(self) -> list[str]:
        return ["net.http"]

    def execute(self, request: ActionRequest) -> Any:
        method = str(request.params.get("method", "GET")).upper()
        call = {"url": request.target, "method": method}
        self.world.http_calls.append(call)
        return {"statusCode": 200, "method": method, "url": request.target, "body": {"accepted": True}}


def make_providers(world: DemoWorld) -> list[Provider]:
    return [DemoDatabaseProvider(world), DemoMcpProvider(world), DemoHttpProvider(world)]


class DemoDbWriteSnapshotStrategy(SnapshotStrategy):
    """Capture DemoWorld table state before a db.write so the action is reversible.

    Restoration goes back through the kernel via a special ``__restore__`` param
    in ``DemoDatabaseProvider.execute`` — keeping the rollback path Gate-mediated
    and audit-logged like any other action (per v2.1 §7).
    """

    def __init__(self, world: DemoWorld) -> None:
        self.world = world

    def supports(self, request: ActionRequest) -> bool:
        return request.action == "db.write"

    def capture(self, request: ActionRequest) -> dict[str, Any]:
        table = self.world.tables.get(request.target, {"dropped": False, "rows": []})
        return {
            "target": request.target,
            "rows": copy.deepcopy(table.get("rows", [])),
            "dropped": bool(table.get("dropped", False)),
        }

    def restore(self, request: ActionRequest, snapshot: dict[str, Any]) -> ActionRequest:
        return ActionRequest(
            action="db.write",
            target=snapshot["target"],
            params={
                "__restore__": True,
                "rows": snapshot["rows"],
                "dropped": snapshot["dropped"],
            },
        )


SNAPSHOT_STORE_DIR = Path("demo/runtime/snapshots")
_snapshot_store: SnapshotStore | None = None


def get_snapshot_store() -> SnapshotStore:
    global _snapshot_store
    if _snapshot_store is None:
        _snapshot_store = SnapshotStore(SNAPSHOT_STORE_DIR, ttl_seconds=3600)
    return _snapshot_store


def clear_snapshots() -> None:
    if SNAPSHOT_STORE_DIR.exists():
        for path in SNAPSHOT_STORE_DIR.glob("*.json"):
            path.unlink(missing_ok=True)


def policy_from_yaml(policy_yaml: str) -> Policy:
    data = yaml.safe_load(policy_yaml)
    if not isinstance(data, dict) or not isinstance(data.get("capabilities"), list):
        raise ValueError("Policy YAML must contain a capabilities list")

    rules: list[CapabilityRule] = []
    for item in data["capabilities"]:
        if not isinstance(item, dict) or "action" not in item or "resource" not in item:
            raise ValueError("Each capability must include action and resource")
        rules.append(
            CapabilityRule(
                action=str(item["action"]),
                resource=str(item["resource"]),
                constraint=item.get("constraint"),
            )
        )
    return Policy(capabilities=rules)


def records_as_dicts(log_path: Path) -> list[dict[str, Any]]:
    return [record_to_dict(record) for record in Log(log_path).read_all()]


def record_to_dict(record: Record) -> dict[str, Any]:
    data = asdict(record)
    return {
        "timestamp": data["timestamp"],
        "action": data["action"],
        "target": data["target"],
        "status": data["status"],
        "error": data.get("error"),
        "duration_ms": data.get("duration_ms"),
    }


def result_to_dict(result: ActionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "data": result.data,
        "error": result.error,
        "record_id": result.record_id,
    }


def request_to_dict(request: ActionRequest) -> dict[str, Any]:
    return {"action": request.action, "target": request.target, "params": request.params}


def last_record(log_path: Path) -> dict[str, Any] | None:
    records = records_as_dicts(log_path)
    return records[-1] if records else None


def kernel_submit(
    *,
    world: DemoWorld,
    policy_yaml: str,
    log_path: Path,
    request: ActionRequest,
    reversible: bool = True,
) -> tuple[ActionResult, dict[str, Any] | None]:
    """Submit a request through the kernel.

    When ``reversible=True`` (default), wraps the kernel in a
    ``ReversibleActionLayer`` so eligible actions (currently ``db.write``)
    populate ``result.record_id`` for one-click rollback.
    """
    kernel = Kernel(
        policy=policy_from_yaml(policy_yaml),
        providers=make_providers(world),
        log_path=log_path,
    )
    try:
        if reversible:
            layer = ReversibleActionLayer(
                kernel=kernel,
                strategies=[DemoDbWriteSnapshotStrategy(world)],
                store=get_snapshot_store(),
            )
            result = layer.submit(request)
        else:
            result = kernel.submit(request)
    finally:
        kernel.close()
    return result, last_record(log_path)


def kernel_rollback(
    *,
    world: DemoWorld,
    policy_yaml: str,
    log_path: Path,
    record_id: str,
) -> tuple[ActionResult, dict[str, Any] | None]:
    kernel = Kernel(
        policy=policy_from_yaml(policy_yaml),
        providers=make_providers(world),
        log_path=log_path,
    )
    try:
        layer = ReversibleActionLayer(
            kernel=kernel,
            strategies=[DemoDbWriteSnapshotStrategy(world)],
            store=get_snapshot_store(),
        )
        result = layer.rollback(record_id)
    finally:
        kernel.close()
    return result, last_record(log_path)


def direct_execute(world: DemoWorld, request: ActionRequest) -> ActionResult:
    providers: dict[str, Provider] = {}
    for provider in make_providers(world):
        for action in provider.actions:
            providers[action] = provider
    selected_provider = providers.get(request.action)
    if selected_provider is None:
        return ActionResult(status="ERROR", error="no provider")
    try:
        return ActionResult(status="OK", data=selected_provider.execute(request))
    except Exception as exc:
        return ActionResult(status="ERROR", error=str(exc))


def planned_request(scenario: str) -> ActionRequest:
    if scenario == "mcp-scholar":
        return ActionRequest(
            action="mcp.call",
            target="scholar/search",
            params={"query": "kernel-mediated agent tool use"},
        )
    if scenario == "http-egress":
        return ActionRequest(
            action="net.http",
            target="https://telemetry.bad.example/collect",
            params={"method": "POST", "body": {"event": "demo"}},
        )
    return ActionRequest(action="db.write", target="prod/users", params={"sql": "DROP TABLE users;"})


def repaired_request(scenario: str) -> ActionRequest | None:
    if scenario == "http-egress":
        return ActionRequest(
            action="net.http",
            target="https://api.example.com/health",
            params={"method": "GET"},
        )
    if scenario == "dangerous-db":
        return ActionRequest(
            action="db.write",
            target="prod/test_sessions",
            params={"sql": "DELETE FROM prod.test_sessions WHERE fixture = true;"},
        )
    return None


def deterministic_step(scenario: str, observation: dict[str, Any] | None = None) -> dict[str, Any]:
    if observation is None:
        request = planned_request(scenario)
        thought = {
            "dangerous-db": "Try the direct cleanup SQL.",
            "mcp-scholar": "Call the configured scholar MCP tool.",
            "http-egress": "Send the telemetry request directly.",
        }.get(scenario, "Choose the first action.")
        return {
            "type": "action",
            "action": request.action,
            "target": request.target,
            "params": request.params,
            "thought": thought,
        }

    result = observation.get("result", {})
    if result.get("status") == "DENIED":
        fixed_request = repaired_request(scenario)
        if fixed_request is not None:
            return {
                "type": "action",
                "action": fixed_request.action,
                "target": fixed_request.target,
                "params": fixed_request.params,
                "thought": "Retry inside the policy-allowed boundary.",
            }

    return {"type": "final", "message": "The kernel-mediated action has completed."}


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    return data


class OpenAICompatiblePlanner:
    def __init__(self, config: LLMConfig | None = None) -> None:
        config = config or LLMConfig()
        self.api_key = normalize_optional(config.api_key) or os.getenv("OPENAI_API_KEY")
        self.base_url = (
            normalize_optional(config.base_url) or os.getenv("OPENAI_BASE_URL") or "https://api.openai-proxy.org"
        ).rstrip("/")
        self.model = normalize_optional(config.model) or os.getenv("OPENAI_MODEL") or "deepseek-v4-flash"

    def configured(self) -> bool:
        return bool(self.api_key)

    async def test_connection(self) -> dict[str, Any]:
        if not self.api_key:
            return {
                "ok": False,
                "baseUrl": self.base_url,
                "model": self.model,
                "error": "OPENAI_API_KEY is required",
            }
        try:
            raw = await self._chat(
                [
                    {"role": "system", "content": "Reply with exactly: Agent Kernel LLM OK"},
                    {"role": "user", "content": "connection test"},
                ],
                temperature=0,
                max_tokens=24,
            )
            return {"ok": True, "baseUrl": self.base_url, "model": self.model, "message": raw.strip()}
        except Exception as exc:
            return {"ok": False, "baseUrl": self.base_url, "model": self.model, "error": str(exc)}

    async def request_agent_step(
        self,
        *,
        scenario: str,
        prompt: str,
        observation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured():
            parsed = deterministic_step(scenario, observation)
            return {"raw": json.dumps(parsed, separators=(",", ":")), "parsed": parsed}

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the planner for an Agent Kernel demo. Return exactly one JSON object. "
                    'Use either {"type":"action","action":string,"target":string,"params":object,'
                    '"thought":string} or {"type":"final","message":string}. '
                    "For the dangerous-db scenario, first demonstrate the risky direct action against prod/users; "
                    "after a DENIED observation, retry within prod/test_sessions. "
                    "For http-egress, first demonstrate an untrusted POST; after DENIED, use "
                    "https://api.example.com/health with GET. For mcp-scholar, call scholar/search."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"scenario": scenario, "user_prompt": prompt, "observation": observation},
                    ensure_ascii=True,
                ),
            },
        ]
        raw = await self._chat(messages, temperature=0, max_tokens=500)
        return {"raw": raw, "parsed": parse_json_object(raw)}

    async def _chat(self, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str:
        def post() -> str:
            body = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            request = urllib.request.Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {detail}") from exc

            choices = payload.get("choices")
            if not choices:
                raise RuntimeError("LLM response did not include choices")
            content = choices[0].get("message", {}).get("content")
            if not isinstance(content, str):
                raise RuntimeError("LLM response did not include message content")
            return content

        return await asyncio.to_thread(post)


def normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class EventBuilder:
    def __init__(self) -> None:
        self.seq = 0

    def event(
        self,
        *,
        lane: str,
        type_: str,
        title: str,
        detail: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        self.seq += 1
        data: dict[str, Any] = {"seq": self.seq, "lane": lane, "type": type_, "title": title}
        if detail is not None:
            data["detail"] = detail
        data.update(extra)
        return data


async def stream_scenario(
    *,
    scenario: str,
    prompt: str,
    mode: str,
    policy_yaml: str,
    log_path: Path,
    llm_config: LLMConfig | None = None,
) -> AsyncIterator[dict[str, Any]]:
    builder = EventBuilder()
    yield builder.event(
        lane="system",
        type_="scenario",
        title=scenario,
        detail=prompt,
        payloads=[{"label": "User prompt", "value": prompt}, {"label": "Mode", "value": mode}],
    )

    if mode == "llm":
        async for event in stream_llm_scenario(
            builder=builder,
            scenario=scenario,
            prompt=prompt,
            policy_yaml=policy_yaml,
            log_path=log_path,
            llm_config=llm_config,
        ):
            yield event
        return

    naive_world = DemoWorld()
    kernel_world = DemoWorld()
    request = planned_request(scenario)

    if mode in {"comparison", "naive"}:
        yield builder.event(
            lane="naive",
            type_="tool-call",
            title="Agent tool call: direct provider.execute",
            detail="The runtime executes the selected tool without policy mediation.",
            request=request_to_dict(request),
            payloads=[
                {
                    "label": "Agent tool call",
                    "value": {"name": "provider.execute", "arguments": request_to_dict(request)},
                }
            ],
        )
        naive_result = direct_execute(naive_world, request)
        yield builder.event(
            lane="naive",
            type_="provider",
            title="Tool output: direct provider result",
            detail="No kernel audit record is written for this bypass path.",
            result=result_to_dict(naive_result),
            world=naive_world.snapshot(),
            payloads=[{"label": "Tool output", "value": result_to_dict(naive_result)}],
        )

    if mode in {"comparison", "kernel"}:
        yield builder.event(
            lane="kernel",
            type_="tool-call",
            title="Agent tool call: kernel.submit",
            detail="The same requested action must pass through the Gate.",
            request=request_to_dict(request),
            payloads=[
                {
                    "label": "Agent tool call",
                    "value": {"name": "kernel.submit", "arguments": request_to_dict(request)},
                }
            ],
        )
        result, record = kernel_submit(
            world=kernel_world,
            policy_yaml=policy_yaml,
            log_path=log_path,
            request=request,
        )
        yield builder.event(
            lane="kernel",
            type_="kernel-decision",
            title=f"Tool output / Kernel observation: {result.status}",
            detail="The kernel returns the tool output to the agent and appends one audit record.",
            request=request_to_dict(request),
            result=result_to_dict(result),
            record=record,
            record_id=result.record_id,
            world=kernel_world.snapshot(),
            payloads=[
                {"label": "Tool output", "value": result_to_dict(result)},
                {"label": "Audit log record", "value": record},
            ],
        )
        if result.status == "DENIED":
            fixed = repaired_request(scenario)
            if fixed is not None:
                yield builder.event(
                    lane="kernel",
                    type_="agent",
                    title="Agent observes denial and chooses next action",
                    detail="The new action stays inside the policy allow-list.",
                    request=request_to_dict(fixed),
                    payloads=[
                        {
                            "label": "Next tool call",
                            "value": {"name": "kernel.submit", "arguments": request_to_dict(fixed)},
                        }
                    ],
                )
                fixed_result, fixed_record = kernel_submit(
                    world=kernel_world,
                    policy_yaml=policy_yaml,
                    log_path=log_path,
                    request=fixed,
                )
                yield builder.event(
                    lane="kernel",
                    type_="kernel-decision",
                    title=f"Tool output / Kernel observation: {fixed_result.status}",
                    detail="The corrected action is authorized and logged.",
                    request=request_to_dict(fixed),
                    result=result_to_dict(fixed_result),
                    record=fixed_record,
                    record_id=fixed_result.record_id,
                    world=kernel_world.snapshot(),
                    payloads=[
                        {"label": "Tool output", "value": result_to_dict(fixed_result)},
                        {"label": "Audit log record", "value": fixed_record},
                    ],
                )

    yield builder.event(
        lane="system",
        type_="done",
        title="Run complete",
        detail="Scenario execution finished.",
        worlds={"naive": naive_world.snapshot(), "kernel": kernel_world.snapshot()},
    )


async def stream_llm_scenario(
    *,
    builder: EventBuilder,
    scenario: str,
    prompt: str,
    policy_yaml: str,
    log_path: Path,
    llm_config: LLMConfig | None,
) -> AsyncIterator[dict[str, Any]]:
    planner = OpenAICompatiblePlanner(llm_config)
    naive_world = DemoWorld()
    kernel_world = DemoWorld()

    yield builder.event(
        lane="kernel",
        type_="user-prompt",
        title="User prompt",
        detail=prompt,
        payloads=[{"label": "User prompt", "value": prompt}],
    )

    step_payload = await planner.request_agent_step(scenario=scenario, prompt=prompt)
    step = step_payload["parsed"]
    request = action_request_from_step(step)
    yield builder.event(
        lane="kernel",
        type_="llm-output",
        title="LLM output: first agent step",
        detail=str(step.get("thought", "Planner selected the first action.")),
        request=request_to_dict(request),
        payloads=[
            {"label": "User prompt", "value": prompt},
            {"label": "Raw LLM output", "value": step_payload["raw"]},
            {"label": "Parsed agent step", "value": step},
            {
                "label": "Planned tool call",
                "value": {"name": "kernel.submit", "arguments": request_to_dict(request)},
            },
        ],
    )

    yield builder.event(
        lane="naive",
        type_="tool-call",
        title="Agent tool call: direct provider.execute",
        detail="The runtime executes the model-selected tool without policy mediation.",
        request=request_to_dict(request),
        payloads=[
            {
                "label": "Agent tool call",
                "value": {"name": "provider.execute", "arguments": request_to_dict(request)},
            }
        ],
    )
    naive_result = direct_execute(naive_world, request)
    yield builder.event(
        lane="naive",
        type_="provider",
        title="Tool output: direct provider result",
        detail="No kernel audit record is written for this bypass path.",
        result=result_to_dict(naive_result),
        world=naive_world.snapshot(),
        payloads=[{"label": "Tool output", "value": result_to_dict(naive_result)}],
    )

    yield builder.event(
        lane="kernel",
        type_="tool-call",
        title="Agent tool call: kernel.submit",
        detail=str(step.get("thought", "Submitting through the Gate.")),
        request=request_to_dict(request),
        payloads=[
            {
                "label": "Agent tool call",
                "value": {"name": "kernel.submit", "arguments": request_to_dict(request)},
            }
        ],
    )
    result, record = kernel_submit(
        world=kernel_world,
        policy_yaml=policy_yaml,
        log_path=log_path,
        request=request,
    )
    observation = {"request": request_to_dict(request), "result": result_to_dict(result)}
    yield builder.event(
        lane="kernel",
        type_="kernel-decision",
        title=f"Tool output / Kernel observation: {result.status}",
        detail="The kernel returns the tool output to the agent and appends one audit record.",
        request=request_to_dict(request),
        result=result_to_dict(result),
        record=record,
        record_id=result.record_id,
        world=kernel_world.snapshot(),
        payloads=[
            {"label": "Tool output", "value": result_to_dict(result)},
            {"label": "Audit log record", "value": record},
            {"label": "Observation for next LLM step", "value": observation},
        ],
    )

    next_payload = await planner.request_agent_step(scenario=scenario, prompt=prompt, observation=observation)
    next_step = next_payload["parsed"]
    yield builder.event(
        lane="kernel",
        type_="llm-output",
        title="LLM output: next agent step",
        detail="The denied kernel result is now the agent observation.",
        payloads=[
            {"label": "Observation input", "value": observation},
            {"label": "Raw LLM output", "value": next_payload["raw"]},
            {"label": "Parsed agent step", "value": next_step},
        ],
    )

    if next_step.get("type") == "action":
        fixed = action_request_from_step(next_step)
        yield builder.event(
            lane="kernel",
            type_="agent",
            title="Agent observes denial and chooses next action",
            detail=str(next_step.get("thought", "Planner selected the next action.")),
            request=request_to_dict(fixed),
            payloads=[
                {
                    "label": "Next tool call",
                    "value": {"name": "kernel.submit", "arguments": request_to_dict(fixed)},
                }
            ],
        )
        yield builder.event(
            lane="kernel",
            type_="tool-call",
            title="Agent tool call: kernel.submit",
            detail=str(next_step.get("thought", "Submitting through the Gate.")),
            request=request_to_dict(fixed),
            payloads=[
                {
                    "label": "Agent tool call",
                    "value": {"name": "kernel.submit", "arguments": request_to_dict(fixed)},
                }
            ],
        )
        fixed_result, fixed_record = kernel_submit(
            world=kernel_world, policy_yaml=policy_yaml, log_path=log_path, request=fixed
        )
        fixed_observation = {"request": request_to_dict(fixed), "result": result_to_dict(fixed_result)}
        yield builder.event(
            lane="kernel",
            type_="kernel-decision",
            title=f"Tool output / Kernel observation: {fixed_result.status}",
            detail="The kernel returns the tool output to the agent and appends one audit record.",
            request=request_to_dict(fixed),
            result=result_to_dict(fixed_result),
            record=fixed_record,
            record_id=fixed_result.record_id,
            world=kernel_world.snapshot(),
            payloads=[
                {"label": "Tool output", "value": result_to_dict(fixed_result)},
                {"label": "Audit log record", "value": fixed_record},
                {"label": "Observation for next LLM step", "value": fixed_observation},
            ],
        )
        final_payload = await planner.request_agent_step(
            scenario=scenario,
            prompt=prompt,
            observation=fixed_observation,
        )
        final_step = final_payload["parsed"]
        yield builder.event(
            lane="kernel",
            type_="llm-output",
            title="LLM output: final response",
            detail="The latest tool output is provided as the agent observation.",
            payloads=[
                {"label": "Observation input", "value": fixed_observation},
                {"label": "Raw LLM output", "value": final_payload["raw"]},
                {"label": "Parsed agent step", "value": final_step},
            ],
        )
        yield builder.event(
            lane="kernel",
            type_="agent-final",
            title="Agent final answer",
            detail=str(final_step.get("message", "Done.")),
            payloads=[{"label": "Final answer", "value": str(final_step.get("message", "Done."))}],
        )

    yield builder.event(
        lane="system",
        type_="done",
        title="Run complete",
        detail="Scenario execution finished.",
        worlds={"naive": naive_world.snapshot(), "kernel": kernel_world.snapshot()},
    )


def action_request_from_step(step: dict[str, Any]) -> ActionRequest:
    if step.get("type") != "action":
        raise ValueError("Agent step is not an action")
    params = step.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("Agent action params must be an object")
    return ActionRequest(
        action=str(step.get("action") or ""),
        target=str(step.get("target") or ""),
        params=params,
    )


def new_log_path() -> Path:
    return Path(tempfile.gettempdir()) / "agent-kernel-workbench" / f"{uuid.uuid4().hex}.jsonl"
