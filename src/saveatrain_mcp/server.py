from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastmcp import Context, FastMCP

from .config import Settings
from .errors import SATError
from .models import Passenger, build_search_params, parse_search_response
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


def _get_sat(ctx: Any) -> SATClient:
    return ctx.lifespan_context["sat"]


def _get_stations(ctx: Any) -> StationsRepo:
    return ctx.lifespan_context["stations"]


@mcp.tool
def ping() -> str:
    """Health check: returns 'ok' when the server is reachable."""
    return "ok"


@mcp.tool
async def search_stations(
    query: str,
    ctx: Context,
    limit: int = 10,
    lang: str = "en",
) -> list[dict[str, Any]] | dict[str, Any]:
    """Search train stations by name. Returns up to `limit` matches with station UID,
    name, country, and location. Use the returned `uid` as origin/destination in search_trains."""
    try:
        stations = _get_stations(ctx)
        return await stations.search(query, limit=limit, lang=lang)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool
async def search_trains(
    origin_uid: str,
    destination_uid: str,
    departure_datetime: datetime,
    passengers: list[Passenger],
    ctx: Context,
    return_datetime: datetime | None = None,
) -> dict[str, Any]:
    """Search for train connections between two stations. Accepts ISO 8601 datetimes.
    Returns a search identifier (needed for sub_routes/tariff_conditions) and a list of
    results with departure/arrival times, duration, price, and provider. Searches expire
    after ~30 minutes."""
    try:
        sat = _get_sat(ctx)
        params = build_search_params(
            origin_uid=origin_uid,
            destination_uid=destination_uid,
            departure_datetime=departure_datetime,
            return_datetime=return_datetime,
            passengers=passengers,
        )
        raw = await sat.request("POST", "/api/searches", json=params)
        if "ok" in raw and raw["ok"] is False:
            return raw
        return parse_search_response(raw).model_dump()
    except SATError as e:
        return {"ok": False, "error": str(e)}


@mcp.tool
async def get_sub_routes(
    search_identifier: str,
    result_id: int,
    ctx: Context,
) -> dict[str, Any]:
    """Get detailed legs, transfers, and fares for a specific search result.
    Requires the search_identifier from search_trains and a result id."""
    try:
        sat = _get_sat(ctx)
        return await sat.request(
            "GET", f"/api/searches/{search_identifier}/results/{result_id}/sub_routes"
        )
    except SATError as e:
        return {"ok": False, "error": str(e)}


@mcp.tool
async def get_tariff_conditions(
    search_identifier: str,
    result_id: int,
    result_fare_id: int,
    ctx: Context,
) -> dict[str, Any]:
    """Get cancellation and exchange rules for a specific fare.
    Requires search_identifier, result_id, and the fare id from sub_routes."""
    try:
        sat = _get_sat(ctx)
        return await sat.request(
            "GET",
            f"/api/searches/{search_identifier}/results/{result_id}"
            f"/tariff_conditions/{result_fare_id}",
        )
    except SATError as e:
        return {"ok": False, "error": str(e)}
