from __future__ import annotations

from typing import Any

import httpx

from .errors import (
    SATAuthError,
    SATNotFoundError,
    SATTimeoutError,
    SATUpstreamError,
)

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class SATClient:
    def __init__(
        self,
        *,
        base_url: str,
        agent_email: str,
        agent_token: str,
        forwarded_for: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ) -> None:
        self._auth_headers = {
            "X-Agent-Email": agent_email,
            "X-Agent-Token": agent_token,
            "X-Forwarded-For": forwarded_for,
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=self._auth_headers,
            timeout=timeout,
            transport=transport,
        )
        # Separate client for unauthenticated healthz - no default headers.
        self._healthz_client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> SATClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()
        await self._healthz_client.aclose()

    async def healthz(self) -> None:
        try:
            resp = await self._healthz_client.get("/healthz")
        except httpx.TimeoutException as e:
            raise SATTimeoutError("timeout calling /healthz") from e
        if resp.status_code >= 400:
            raise SATUpstreamError(f"/healthz returned {resp.status_code}")

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as e:
            raise SATTimeoutError(f"timeout calling {method} {path}") from e

        status = resp.status_code

        if 200 <= status < 300:
            if not resp.content:
                return {}
            return resp.json()

        body = _safe_json(resp)

        if status == 422:
            return {
                "ok": False,
                "error": {"type": "validation", "status": 422, "details": body},
            }
        if status in (401, 403):
            raise SATAuthError(f"{status}: {body}")
        if status == 404:
            raise SATNotFoundError(f"404: {body}")
        if status >= 500:
            raise SATUpstreamError(f"{status}: {body}")

        # Other 4xx fall through to upstream error - unexpected for our use.
        raise SATUpstreamError(f"unexpected {status}: {body}")


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text
