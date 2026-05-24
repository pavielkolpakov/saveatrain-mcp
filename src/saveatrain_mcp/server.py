from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from .config import Settings
from .sat_client import SATClient
from .stations import StationsRepo


async def startup_check(*, sat: Any, stations: Any) -> None:
    """Ping both backends. Raise on first failure - server should not boot."""
    await stations.ping()
    await sat.healthz()


def _build_sat(settings: Settings) -> SATClient:
    return SATClient(
        base_url=str(settings.sat_api_base_url),
        agent_email=settings.sat_agent_email,
        agent_token=settings.sat_agent_token.get_secret_value(),
        forwarded_for=settings.sat_forwarded_for,
    )


def _build_stations(settings: Settings) -> StationsRepo:
    return StationsRepo(mongo_uri=settings.mongo_uri, db_name=settings.mongo_db)


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    settings = Settings()
    sat = _build_sat(settings)
    stations = _build_stations(settings)
    try:
        await startup_check(sat=sat, stations=stations)
        yield {"sat": sat, "stations": stations, "settings": settings}
    finally:
        await sat.aclose()
        await stations.aclose()


mcp = FastMCP("saveatrain-mcp", lifespan=lifespan)


@mcp.tool
def ping() -> str:
    """Health check: returns 'ok' when the server is reachable."""
    return "ok"
