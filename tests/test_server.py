from datetime import datetime

import pytest

from saveatrain_mcp.errors import SATNotFoundError, SATTimeoutError, SATUpstreamError
from saveatrain_mcp.server import (
    get_sub_routes,
    get_tariff_conditions,
    ping,
    search_stations,
    search_trains,
    startup_check,
)


class FakeSAT:
    def __init__(self, raise_exc=None, response=None):
        self.raise_exc = raise_exc
        self.response = response or {}
        self.healthz_called = False
        self.last_request = None

    async def healthz(self):
        self.healthz_called = True
        if self.raise_exc:
            raise self.raise_exc

    async def request(self, method, path, **kwargs):
        self.last_request = (method, path, kwargs)
        if self.raise_exc:
            raise self.raise_exc
        return self.response


class FakeStations:
    def __init__(self, raise_exc=None, results=None):
        self.raise_exc = raise_exc
        self.results = results or []
        self.ping_called = False
        self.last_search = None

    async def ping(self):
        self.ping_called = True
        if self.raise_exc:
            raise self.raise_exc

    async def search(self, query, limit=10, lang="en"):
        self.last_search = (query, limit, lang)
        if self.raise_exc:
            raise self.raise_exc
        return self.results


class FakeContext:
    def __init__(self, sat=None, stations=None):
        self.lifespan_context = {}
        if sat:
            self.lifespan_context["sat"] = sat
        if stations:
            self.lifespan_context["stations"] = stations


async def test_startup_check_pings_both():
    sat = FakeSAT()
    stations = FakeStations()
    await startup_check(sat=sat, stations=stations)
    assert sat.healthz_called
    assert stations.ping_called


async def test_startup_check_fails_when_mongo_ping_fails():
    sat = FakeSAT()
    stations = FakeStations(raise_exc=RuntimeError("mongo down"))
    with pytest.raises(RuntimeError, match="mongo down"):
        await startup_check(sat=sat, stations=stations)


async def test_startup_check_fails_when_sat_healthz_fails():
    sat = FakeSAT(raise_exc=SATUpstreamError("sat down"))
    stations = FakeStations()
    with pytest.raises(SATUpstreamError):
        await startup_check(sat=sat, stations=stations)


def test_ping_tool_returns_ok():
    assert ping() == "ok"


# --- search_stations ---


async def test_search_stations_returns_results():
    stations = FakeStations(
        results=[{"name": "London St Pancras", "uid": "SAT_LSP", "country": "UK", "location": None}]
    )
    ctx = FakeContext(stations=stations)
    result = await search_stations(query="Lond", ctx=ctx)
    assert result == [
        {"name": "London St Pancras", "uid": "SAT_LSP", "country": "UK", "location": None}
    ]
    assert stations.last_search == ("Lond", 10, "en")


async def test_search_stations_passes_limit_and_lang():
    stations = FakeStations(results=[])
    ctx = FakeContext(stations=stations)
    await search_stations(query="Par", limit=3, lang="fr", ctx=ctx)
    assert stations.last_search == ("Par", 3, "fr")


async def test_search_stations_returns_error_on_exception():
    stations = FakeStations(raise_exc=RuntimeError("mongo down"))
    ctx = FakeContext(stations=stations)
    result = await search_stations(query="Lon", ctx=ctx)
    assert result["ok"] is False
    assert "mongo down" in result["error"]


# --- search_trains ---


SEARCH_RESPONSE = {
    "identifier": "vAa4xK",
    "complete": True,
    "expiration_time_left": 1800,
    "route": {},
    "departure_datetime": "2025-03-12 10:00",
    "return_departure_datetime": None,
    "is_beginning": True,
    "is_ending": False,
    "results": [
        {
            "id": 777,
            "identifier": "internal",
            "departure_datetime": "2025-03-12 10:25",
            "arrival_datetime": "2025-03-12 12:22",
            "duration": 117,
            "best_price": 29.0,
            "selected": False,
            "provider": {"name": "Nsi"},
            "changes_count": 0,
        }
    ],
}


async def test_search_trains_posts_and_returns_trimmed():
    from saveatrain_mcp.models import Passenger

    sat = FakeSAT(response=SEARCH_RESPONSE)
    ctx = FakeContext(sat=sat)
    result = await search_trains(
        origin_uid="SAT_A",
        destination_uid="SAT_B",
        departure_datetime=datetime(2025, 3, 12, 10, 0),
        passengers=[Passenger(type="adult")],
        ctx=ctx,
    )
    assert result["search_identifier"] == "vAa4xK"
    assert result["complete"] is True
    assert result["expiration_time_left"] == 1800
    assert len(result["results"]) == 1
    assert result["results"][0]["provider"] == "Nsi"
    # Trimmed fields should not be present
    assert "route" not in result
    assert "is_beginning" not in result

    method, path, kwargs = sat.last_request
    assert method == "POST"
    assert path == "/api/searches"


async def test_search_trains_passes_through_422():
    sat = FakeSAT(
        response={
            "ok": False,
            "error": {"type": "validation", "status": 422, "details": {}},
        }
    )
    ctx = FakeContext(sat=sat)
    result = await search_trains(
        origin_uid="SAT_A",
        destination_uid="SAT_B",
        departure_datetime=datetime(2025, 3, 12, 10, 0),
        passengers=[],
        ctx=ctx,
    )
    assert result["ok"] is False


async def test_search_trains_returns_error_on_timeout():
    sat = FakeSAT(raise_exc=SATTimeoutError("timeout"))
    ctx = FakeContext(sat=sat)
    result = await search_trains(
        origin_uid="SAT_A",
        destination_uid="SAT_B",
        departure_datetime=datetime(2025, 3, 12, 10, 0),
        passengers=[],
        ctx=ctx,
    )
    assert result["ok"] is False
    assert "timeout" in result["error"]


# --- get_sub_routes ---


async def test_get_sub_routes_returns_full_payload():
    payload = {"status": "success", "data": {"legs": [{"id": "leg_1"}]}}
    sat = FakeSAT(response=payload)
    ctx = FakeContext(sat=sat)
    result = await get_sub_routes(search_identifier="abc", result_id=777, ctx=ctx)
    assert result == payload
    method, path, _ = sat.last_request
    assert method == "GET"
    assert path == "/api/searches/abc/results/777/sub_routes"


async def test_get_sub_routes_returns_error_on_not_found():
    sat = FakeSAT(raise_exc=SATNotFoundError("404: not found"))
    ctx = FakeContext(sat=sat)
    result = await get_sub_routes(search_identifier="abc", result_id=777, ctx=ctx)
    assert result["ok"] is False
    assert "not found" in result["error"]


# --- get_tariff_conditions ---


async def test_get_tariff_conditions_returns_full_payload():
    payload = {"conditions": "non-refundable", "fee": 10.0}
    sat = FakeSAT(response=payload)
    ctx = FakeContext(sat=sat)
    result = await get_tariff_conditions(
        search_identifier="abc", result_id=777, result_fare_id=99, ctx=ctx
    )
    assert result == payload
    method, path, _ = sat.last_request
    assert method == "GET"
    assert path == "/api/searches/abc/results/777/tariff_conditions/99"


async def test_get_tariff_conditions_returns_error_on_not_found():
    sat = FakeSAT(raise_exc=SATNotFoundError("404: not found"))
    ctx = FakeContext(sat=sat)
    result = await get_tariff_conditions(
        search_identifier="abc", result_id=777, result_fare_id=99, ctx=ctx
    )
    assert result["ok"] is False
    assert "not found" in result["error"]


async def test_get_tariff_conditions_returns_error_on_upstream():
    sat = FakeSAT(raise_exc=SATUpstreamError("503: down"))
    ctx = FakeContext(sat=sat)
    result = await get_tariff_conditions(
        search_identifier="abc", result_id=777, result_fare_id=99, ctx=ctx
    )
    assert result["ok"] is False
    assert "503" in result["error"]
