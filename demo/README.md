# Agent Kernel Workbench Demo

Interactive demo for the v2 Agent OS Kernel design. The backend uses the real
`agent_os_kernel.Kernel`, policy matcher, provider interface, and JSONL audit
log. The external world is mocked so the browser can show safe, repeatable
effects.

For the full guide, see
[`docs/agent-kernel-workbench-demo.md`](../docs/agent-kernel-workbench-demo.md).

## Quick Start

Backend:

```bash
uv sync --all-extras
uv pip install -r demo/backend/requirements.txt
uv run uvicorn demo.backend.app:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd demo/frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>.

## Optional LLM Agent Loop

The demo works without a model by using deterministic scenario actions.

To enable the OpenAI-compatible agent-loop mode in the browser, fill the
`LLM Config` panel:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

Then click `Test LLM`.

Common model suggestions are available in the model field, including
`gpt-5.5`, `kimi-k2.6`, `qwen3.6-flash`, and `glm-5.1`; custom model names are
also accepted.

You can also set backend environment variables:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai-proxy.org"
export OPENAI_MODEL="deepseek-v4-flash"
```

Do not place API keys in committed files or Vite env variables.

## Main Browser Flow

1. Open <http://127.0.0.1:5173>.
2. Select `Dangerous DB Cleanup`.
3. Select `LLM agent loop if configured`.
4. Fill `LLM Config` and click `Test LLM`.
5. Click `Reset world and logs`.
6. Click `Run`.

The Kernel lane should show `User prompt`, raw `LLM output`, `Agent tool call`,
`Tool output / Kernel observation`, a corrected next LLM step, and the final
answer.
