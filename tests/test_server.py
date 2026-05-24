import pytest

from saveatrain_mcp.errors import SATUpstreamError
from saveatrain_mcp.server import ping, startup_check


class FakeSAT:
    def __init__(self, raise_exc=None):
        self.raise_exc = raise_exc
        self.healthz_called = False

    async def healthz(self):
        self.healthz_called = True
        if self.raise_exc:
            raise self.raise_exc


class FakeStations:
    def __init__(self, raise_exc=None):
        self.raise_exc = raise_exc
        self.ping_called = False

    async def ping(self):
        self.ping_called = True
        if self.raise_exc:
            raise self.raise_exc


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
