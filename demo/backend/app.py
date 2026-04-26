"""FastAPI app for the Agent Kernel Workbench demo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_os_kernel.models import ActionRequest
from demo.backend.runtime import (
    DEFAULT_POLICY_YAML,
    SCENARIOS,
    DemoWorld,
    LLMConfig,
    OpenAICompatiblePlanner,
    clear_snapshots,
    kernel_rollback,
    kernel_submit,
    records_as_dicts,
    request_to_dict,
    result_to_dict,
    stream_scenario,
)


class RunRequest(BaseModel):
    scenario: str
    prompt: str
    mode: str = "comparison"
    policy_yaml: str = Field(alias="policyYaml")
    reset_world: bool = Field(default=True, alias="resetWorld")
    llm_api_key: str | None = Field(default=None, alias="llmApiKey")
    llm_base_url: str | None = Field(default=None, alias="llmBaseUrl")
    llm_model: str | None = Field(default=None, alias="llmModel")


class ManualSubmitRequest(BaseModel):
    action: str
    target: str
    params: dict[str, Any] = Field(default_factory=dict)
    policy_yaml: str = Field(alias="policyYaml")


class LLMTestRequest(BaseModel):
    api_key: str | None = Field(default=None, alias="apiKey")
    base_url: str | None = Field(default=None, alias="baseUrl")
    model: str | None = None


class RollbackRequest(BaseModel):
    record_id: str = Field(alias="recordId")
    policy_yaml: str = Field(alias="policyYaml")


app = FastAPI(title="Agent Kernel Workbench Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

demo_world = DemoWorld()
runtime_dir = Path("demo/runtime")
runtime_dir.mkdir(parents=True, exist_ok=True)
log_path = runtime_dir / "audit.jsonl"
runs: dict[str, RunRequest] = {}


@app.get("/api/scenarios")
def list_scenarios() -> list[dict[str, str]]:
    return SCENARIOS


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/policy/default")
def get_default_policy() -> dict[str, str]:
    return {"policyYaml": DEFAULT_POLICY_YAML}


@app.get("/api/world")
def get_world() -> dict[str, Any]:
    return demo_world.snapshot()


@app.post("/api/world/reset")
def reset_world() -> dict[str, Any]:
    demo_world.reset()
    if log_path.exists():
        log_path.unlink()
    clear_snapshots()
    return {"world": demo_world.snapshot(), "logs": []}


@app.get("/api/logs")
def get_logs() -> list[dict[str, Any]]:
    return records_as_dicts(log_path)


@app.post("/api/kernel/submit")
def submit_manual(payload: ManualSubmitRequest) -> dict[str, Any]:
    try:
        result, record = kernel_submit(
            world=demo_world,
            policy_yaml=payload.policy_yaml,
            log_path=log_path,
            request=ActionRequest(action=payload.action, target=payload.target, params=payload.params),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "request": request_to_dict(ActionRequest(action=payload.action, target=payload.target, params=payload.params)),
        "result": result_to_dict(result),
        "record": record,
        "world": demo_world.snapshot(),
    }


@app.post("/api/llm/test")
async def test_llm_config(payload: LLMTestRequest) -> dict[str, Any]:
    planner = OpenAICompatiblePlanner(
        LLMConfig(api_key=payload.api_key, base_url=payload.base_url, model=payload.model)
    )
    return await planner.test_connection()


@app.post("/api/kernel/rollback")
def rollback_action(payload: RollbackRequest) -> dict[str, Any]:
    try:
        result, record = kernel_rollback(
            world=demo_world,
            policy_yaml=payload.policy_yaml,
            log_path=log_path,
            record_id=payload.record_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "result": result_to_dict(result),
        "record": record,
        "world": demo_world.snapshot(),
    }


@app.post("/api/runs")
def create_run(payload: RunRequest) -> dict[str, str]:
    if payload.scenario not in {scenario["id"] for scenario in SCENARIOS}:
        raise HTTPException(status_code=400, detail="unknown scenario")
    run_id = uuid4().hex
    runs[run_id] = payload
    return {"runId": run_id}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    payload = runs.pop(run_id, None)
    if payload is None:
        raise HTTPException(status_code=404, detail="unknown run")
    if payload.reset_world:
        demo_world.reset()

    async def generate() -> Any:
        try:
            async for event in stream_scenario(
                scenario=payload.scenario,
                prompt=payload.prompt,
                mode=payload.mode,
                policy_yaml=payload.policy_yaml,
                log_path=log_path,
                llm_config=LLMConfig(
                    api_key=payload.llm_api_key,
                    base_url=payload.llm_base_url,
                    model=payload.llm_model,
                ),
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            error = {"seq": 9999, "lane": "system", "type": "error", "title": "Run failed", "detail": str(exc)}
            yield f"data: {json.dumps(error)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
