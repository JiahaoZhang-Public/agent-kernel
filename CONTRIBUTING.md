# Contributing to Agent OS Kernel

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/JiahaoZhang-Public/agent-kernel.git
cd agent-kernel

# Install dependencies (requires uv)
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install
```

## Development Workflow

1. **Create a branch** from `main` for your changes
2. **Make your changes** following the code style guidelines below
3. **Run tests** to ensure nothing is broken
4. **Open a pull request** with a clear description of your changes

## Code Style

- **Formatter**: [Ruff](https://docs.astral.sh/ruff/) (line length: 120)
- **Linter**: Ruff with strict rules (E, F, W, I, N, UP, B, A, SIM)
- **Type checker**: mypy in strict mode
- **Type hints**: Required on all functions and parameters

Run all checks:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

## Testing

All changes must include appropriate tests. We maintain 80%+ coverage (currently 96%+).

```bash
# Run tests with coverage
uv run pytest --cov=src/agent_os_kernel

# Run a specific test file
uv run pytest tests/test_kernel.py -v
```

## Pull Request Guidelines

- Keep PRs focused on a single change
- Write clear commit messages
- Ensure all CI checks pass before requesting review
- Update documentation if your change affects user-facing behavior
- Update the changelog (`docs/user/changelog.md`) for notable changes

## Architecture

Before making changes, familiarize yourself with the design documents:

- [Kernel Design v2.1](docs/research/design/v2.1/Kernel_Design_v2.1.md) — current design spec
- [Agent Loop Design v2.2](docs/research/design/v2.2/Kernel_Design_v2.2.md) — agent loop spec

Key principles:

- `kernel.submit()` is the **sole execution path** for all tool calls
- `ToolDef` contains **zero execution logic** — it is pure metadata
- Every `submit()` call produces exactly **one log record**
- Policy **default deny** — only explicitly allowed actions pass

## Reporting Issues

Use [GitHub Issues](https://github.com/JiahaoZhang-Public/agent-kernel/issues) for bug reports and feature requests.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
