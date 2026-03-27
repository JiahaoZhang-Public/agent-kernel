"""HTTP provider for the Agent OS Kernel.

Handles net.http actions — makes HTTP requests.
"""

from __future__ import annotations

import json as json_mod
import urllib.error
import urllib.request
from typing import Any

from agent_os_kernel.models import ActionRequest
from agent_os_kernel.providers.base import Provider

DEFAULT_TIMEOUT = 30


class HttpProvider(Provider):
    """Provider for HTTP requests using urllib (no external dependencies)."""

    @property
    def actions(self) -> list[str]:
        return ["net.http"]

    def execute(self, request: ActionRequest) -> Any:
        url = request.target
        method = request.params.get("method", "GET").upper()
        headers = request.params.get("headers", {})
        body = request.params.get("body")
        timeout = request.params.get("timeout", DEFAULT_TIMEOUT)

        data = None
        if body is not None:
            if isinstance(body, dict | list):
                data = json_mod.dumps(body).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")
            elif isinstance(body, str):
                data = body.encode("utf-8")
            else:
                data = body

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
                response_body = response.read().decode("utf-8")
                return {
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "body": response_body,
                }
        except urllib.error.HTTPError as e:
            return {
                "status_code": e.code,
                "headers": dict(e.headers) if e.headers else {},
                "body": e.read().decode("utf-8"),
            }
