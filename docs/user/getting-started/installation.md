# Installation

## Prerequisites

- Python >= 3.10

## Install from PyPI

```bash
pip install py-agent-kernel
```

## Install from Source (for development)

Requires [uv](https://docs.astral.sh/uv/) package manager.

```bash
# Clone the repository
git clone https://github.com/JiahaoZhang-Public/agent-kernel.git
cd agent-kernel

# Install all dependencies (including dev, test, docs)
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install
```

## Verify

```bash
# If installed from PyPI
python -c "from agent_os_kernel import Kernel; print('OK')"

# If installed from source
uv run pytest
```
