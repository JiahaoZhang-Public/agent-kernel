# Guides

## Policy Configuration

The kernel uses YAML policy files to define what actions an agent is allowed to perform. The policy follows a **default-deny** model — any action not explicitly permitted is blocked.

### Policy Structure

```yaml
capabilities:
  - action: <action_type>
    resource: <resource_pattern>
    constraint:           # optional
      <key>: <value>
```

### Action Types

| Action | Provider | Description |
|---|---|---|
| `fs.read` | FilesystemProvider | Read file contents |
| `fs.write` | FilesystemProvider | Write/create files |
| `fs.delete` | FilesystemProvider | Delete files |
| `proc.exec` | ProcessProvider | Execute shell commands |
| `net.http` | HttpProvider | Make HTTP requests |
| `mcp.call` | McpProvider | Call MCP server tools |

### Resource Patterns

Resources use glob-style matching:
- `*` matches any single path segment
- `**` matches any number of path segments
- Exact strings match literally

Examples:
- `/workspace/**` — matches everything under `/workspace/`
- `https://api.example.com/**` — matches any URL under that domain
- `git` — matches only the exact string "git"
- `*/search` — matches "scholar/search", "web/search", etc.

### Constraints

Constraints add additional parameter-level restrictions:

```yaml
- action: net.http
  resource: https://api.example.com/**
  constraint:
    method: GET    # only GET requests allowed
```

### Example Policies

See the `configs/` directory for ready-to-use policy templates:
- `example_policy.yaml` — balanced read/write with restricted network
- `restrictive_policy.yaml` — read-only filesystem, no network
- `permissive_policy.yaml` — broad access for trusted environments

## Custom Providers

To add a custom action type, implement the `Provider` base class:

```python
from agent_os_kernel.providers.base import Provider
from agent_os_kernel.models import ActionRequest

class DatabaseProvider(Provider):
    @property
    def actions(self) -> list[str]:
        return ["db.query", "db.write"]

    def execute(self, request: ActionRequest):
        if request.action == "db.query":
            return self._query(request.target, request.params)
        elif request.action == "db.write":
            return self._write(request.target, request.params)
```

Register it when creating the kernel:

```python
kernel = Kernel(
    policy="policy.yaml",
    providers=[FilesystemProvider(), DatabaseProvider()],
)
```

## MCP Integration

The kernel supports calling MCP (Model Context Protocol) servers:

```python
from agent_os_kernel.providers.mcp import McpProvider

mcp = McpProvider(servers={
    "filesystem": {
        "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
    },
    "scholar": {
        "command": ["python", "-m", "scholar_mcp_server"],
        "env": {"API_KEY": "..."},
    },
})

kernel = Kernel(
    policy="policy.yaml",
    providers=[mcp],
)

# Target format: "server_name/tool_name"
result = kernel.submit(ActionRequest(
    action="mcp.call",
    target="scholar/search",
    params={"arguments": {"query": "AI safety"}},
))
```

## Reversible Actions

The Reversible Action Layer provides snapshot-based rollback for destructive operations. See the [Quickstart](../getting-started/quickstart.md) for usage examples.

Key concepts:
- **Snapshot strategies** capture state before execution
- **Rollback goes through the kernel** — authorized and logged like any action
- **TTL-based expiration** — snapshots expire after 1 hour by default
- **Best-effort** — not all actions are reversible
