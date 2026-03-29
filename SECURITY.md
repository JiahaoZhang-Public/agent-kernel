# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.4.x   | Yes       |
| < 0.4   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email the maintainers or use [GitHub Security Advisories](https://github.com/JiahaoZhang-Public/agent-kernel/security/advisories/new) to report privately
3. Include steps to reproduce, impact assessment, and any suggested fixes

We aim to acknowledge reports within 48 hours and provide a fix or mitigation plan within 7 days for critical issues.

## Scope

The Agent OS Kernel enforces a security boundary for LLM agent tool calls. Security-relevant areas include:

- **Gate policy enforcement** — bypasses to `kernel.submit()` or default-deny logic
- **Audit log integrity** — tampering, omission, or corruption of log records
- **Rollback mechanism** — unauthorized or incorrect state restoration
- **Provider isolation** — tool providers escaping their declared capabilities
