import httpx
import pytest

from saveatrain_mcp.errors import (
    SATAuthError,
    SATNotFoundError,
    SATTimeoutError,
    SATUpstreamError,
)
from saveatrain_mcp.sat_client import SATClient


def _client(handler) -> SATClient:
    transport = httpx.MockTransport(handler)
    return SATClient(
        base_url="https://vendor.example.com",
        agent_email="agent@example.com",
        agent_token="tok_abc",
        forwarded_for="203.0.113.5",
        transport=transport,
    )


async def test_returns_payload_on_2xx():
    def handler(req):
        return httpx.Response(200, json={"hello": "world"})

    async with _client(handler) as c:
        result = await c.request("GET", "/api/v1/anything")
    assert result == {"hello": "world"}


async def test_sends_auth_headers():
    captured = {}

    def handler(req):
        captured["headers"] = req.headers
        return httpx.Response(200, json={})

    async with _client(handler) as c:
        await c.request("GET", "/api/v1/anything")

    h = captured["headers"]
    assert h["X-Agent-Email"] == "agent@example.com"
    assert h["X-Agent-Token"] == "tok_abc"
    assert h["X-Forwarded-For"] == "203.0.113.5"
    assert h["Accept"] == "application/json"


async def test_returns_structured_error_on_422():
    def handler(req):
        return httpx.Response(422, json={"errors": {"origin": ["is required"]}})

    async with _client(handler) as c:
        result = await c.request("POST", "/api/v1/searches", json={})

    assert result == {
        "ok": False,
        "error": {
            "type": "validation",
            "status": 422,
            "details": {"errors": {"origin": ["is required"]}},
        },
    }


@pytest.mark.parametrize("status", [401, 403])
async def test_raises_auth_error(status):
    def handler(req):
        return httpx.Response(status, json={"errors": "X-Agent-Token is invalid"})

    async with _client(handler) as c:
        with pytest.raises(SATAuthError):
            await c.request("GET", "/api/v1/anything")


async def test_raises_not_found_on_404():
    def handler(req):
        return httpx.Response(404, json={"errors": "missing"})

    async with _client(handler) as c:
        with pytest.raises(SATNotFoundError):
            await c.request("GET", "/api/v1/anything")


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_raises_upstream_on_5xx(status):
    def handler(req):
        return httpx.Response(status, text="boom")

    async with _client(handler) as c:
        with pytest.raises(SATUpstreamError):
            await c.request("GET", "/api/v1/anything")


async def test_raises_timeout():
    def handler(req):
        raise httpx.TimeoutException("slow", request=req)

    async with _client(handler) as c:
        with pytest.raises(SATTimeoutError):
            await c.request("GET", "/api/v1/anything")


async def test_healthz_no_auth_needed():
    captured = {}

    def handler(req):
        captured["headers"] = req.headers
        captured["url"] = str(req.url)
        return httpx.Response(200, text="ok")

    async with _client(handler) as c:
        await c.healthz()

    # /healthz hits the right path and does NOT carry the auth headers
    assert captured["url"].endswith("/healthz")
    assert "X-Agent-Token" not in captured["headers"]
    assert "X-Agent-Email" not in captured["headers"]


async def test_healthz_raises_upstream_on_non_2xx():
    def handler(req):
        return httpx.Response(503, text="down")

    async with _client(handler) as c:
        with pytest.raises(SATUpstreamError):
            await c.healthz()


async def test_post_searches_sends_json_and_returns_payload():
    captured = {}

    def handler(req):
        captured["method"] = req.method
        captured["url"] = str(req.url)
        captured["body"] = req.content
        return httpx.Response(200, json={"identifier": "abc123", "results": []})

    async with _client(handler) as c:
        result = await c.request("POST", "/api/v1/searches", json={"search": {}})

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/api/v1/searches")
    assert result["identifier"] == "abc123"


async def test_get_sub_routes_returns_payload():
    def handler(req):
        assert req.method == "GET"
        assert "/searches/abc/results/777/sub_routes" in str(req.url)
        return httpx.Response(200, json={"status": "success", "data": {"legs": []}})

    async with _client(handler) as c:
        result = await c.request("GET", "/api/v1/searches/abc/results/777/sub_routes")

    assert result == {"status": "success", "data": {"legs": []}}


async def test_get_sub_routes_404_raises_not_found():
    def handler(req):
        return httpx.Response(404, json={"errors": "not found"})

    async with _client(handler) as c:
        with pytest.raises(SATNotFoundError):
            await c.request("GET", "/api/v1/searches/abc/results/777/sub_routes")


async def test_get_tariff_conditions_returns_payload():
    def handler(req):
        assert "/tariff_conditions/99" in str(req.url)
        return httpx.Response(200, json={"conditions": "non-refundable"})

    async with _client(handler) as c:
        result = await c.request("GET", "/api/v1/searches/abc/results/777/tariff_conditions/99")

    assert result == {"conditions": "non-refundable"}
