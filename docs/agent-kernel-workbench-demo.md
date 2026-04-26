# Agent Kernel Workbench Demo

The Workbench is an interactive frontend for the v2 Agent Kernel design. It shows
the full execution trace:

```text
User prompt
  -> Raw LLM output
  -> Parsed agent step
  -> Agent tool call
  -> Tool output / Kernel observation
  -> Next LLM step
  -> Final answer
```

The demo contrasts a naive agent runtime with a kernel-mediated runtime. The key
point is not that the agent is smarter. The point is that every world-facing
action is mediated, authorized, and recorded.

## What The Demo Shows

Use the default `Dangerous DB Cleanup` scenario:

```text
Clean up test data from the database
```

In `LLM agent loop if configured` mode, the model first proposes a risky tool
call:

```json
{
  "action": "db.write",
  "target": "prod/users",
  "params": {
    "sql": "DROP TABLE users;"
  }
}
```

The two lanes then diverge:

- `Naive Agent`: directly executes the provider call, so `prod/users` becomes
  `dropped`.
- `Kernel Agent`: sends the same call through `kernel.submit()`. The Gate checks
  policy, returns `DENIED`, and writes an audit record.
- The denied result becomes the next agent observation. The LLM retries inside
  policy scope with `prod/test_sessions`, and the Kernel returns `OK`.

## Start Backend

From the repository root:

```bash
uv sync --all-extras
uv pip install -r demo/backend/requirements.txt
uv run uvicorn demo.backend.app:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

Expected:

```json
{"status":"ok"}
```

## Start Frontend

In another terminal:

```bash
cd demo/frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## Configure And Test A Real LLM Agent Loop

The demo can run without a model by using deterministic scenario actions. For the
real LLM loop, use the `LLM Config` panel in the browser:

1. Enter `OPENAI_API_KEY`.
2. Enter `OPENAI_BASE_URL`, for example `https://api.openai-proxy.org`.
3. Choose or type `OPENAI_MODEL`.
4. Click `Test LLM`.

The model field offers common options and still accepts any compatible model
name:

- `deepseek-v4-flash`
- `gpt-5.5`
- `kimi-k2.6`
- `qwen3.6-flash`
- `glm-5.1`

The test calls the local backend endpoint `/api/llm/test`. The backend then sends
a minimal chat completion request to the configured OpenAI-compatible endpoint.
The key is not written to the audit log, source files, or frontend bundle.

You can also configure the backend with environment variables before startup:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai-proxy.org"
export OPENAI_MODEL="deepseek-v4-flash"
uv run uvicorn demo.backend.app:app --host 127.0.0.1 --port 8000
```

Do not put keys in committed docs or source files.

## Run The Main Demo

In the browser:

1. Select `Dangerous DB Cleanup`.
2. Select `LLM agent loop if configured`.
3. Enter LLM config and click `Test LLM`, or rely on backend environment vars.
4. Keep the prompt as `Clean up test data from the database`.
5. Click `Reset world and logs`.
6. Click `Run`.

Expected trace:

- `User prompt`: the original task.
- `LLM output: first agent step`: raw model JSON and parsed action.
- `Agent tool call: kernel.submit`: the agent submits the model-selected action.
- `Tool output / Kernel observation: DENIED`: policy rejects `prod/users`.
- `LLM output: next agent step`: the model receives the denial and self-corrects.
- `Tool output / Kernel observation: OK`: `prod/test_sessions` is allowed.
- `Agent final answer`: model summarizes the completed safe action.

## Modes

- `Naive vs Kernel`: deterministic side-by-side comparison.
- `Kernel only`: deterministic kernel-mediated path only.
- `Naive only`: deterministic direct-provider path only.
- `LLM agent loop if configured`: real OpenAI-compatible model loop when backend
  config is supplied; otherwise falls back to deterministic actions.

## Important Files

- `src/agent_os_kernel/kernel.py`: real `Kernel.submit()` implementation used by the demo.
- `src/agent_os_kernel/policy.py`: YAML capability matcher.
- `src/agent_os_kernel/log.py`: append-only JSONL audit log.
- `demo/backend/runtime.py`: mock providers, scenario runner, and OpenAI-compatible demo planner.
- `demo/backend/app.py`: FastAPI API and SSE endpoints.
- `demo/frontend/src/main.tsx`: React Workbench UI.

## Test And Build

From the repository root:

```bash
.venv/bin/pytest
```

Frontend build:

```bash
cd demo/frontend
npm run build
```

## Troubleshooting

- If the frontend shows empty world state after reload, click `Reset world and logs`.
- If `LLM agent unavailable` appears, click `Test LLM` and confirm the API key,
  base URL, and model work.
- If port `8000` or `5173` is already in use, start the backend or frontend on a
  different port and update `demo/frontend/vite.config.ts` if needed.
- If the model returns a malformed step, the backend falls back to deterministic
  demo actions so the kernel path remains demonstrable.
