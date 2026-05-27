from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

PASSENGER_TYPE_MAP = {
    "adult": "Search::PassengerType::Adult",
    "youth": "Search::PassengerType::Youth",
    "senior": "Search::PassengerType::Senior",
    "child": "Search::PassengerType::Child",
    "infant": "Search::PassengerType::Infant",
}


class Passenger(BaseModel):
    type: Literal["adult", "youth", "senior", "child", "infant"]
    age: int | None = None


def build_passengers_attributes(passengers: list[Passenger]) -> dict[str, Any]:
    return {
        str(i): {
            "age": p.age,
            "passenger_type_attributes": {"type": PASSENGER_TYPE_MAP[p.type]},
        }
        for i, p in enumerate(passengers)
    }


def _format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


class TrainResult(BaseModel):
    id: int
    departure_datetime: str
    arrival_datetime: str
    duration: int
    best_price: float
    changes_count: int
    provider: str


class SearchTrainsResponse(BaseModel):
    search_identifier: str
    complete: bool
    expiration_time_left: int
    results: list[TrainResult]


def parse_search_response(raw: dict[str, Any]) -> SearchTrainsResponse:
    results = [
        TrainResult(
            id=r["id"],
            departure_datetime=r["departure_datetime"],
            arrival_datetime=r["arrival_datetime"],
            duration=r["duration"],
            best_price=r["best_price"],
            changes_count=r["changes_count"],
            provider=r.get("provider", {}).get("name", "unknown"),
        )
        for r in raw.get("results", [])
    ]
    return SearchTrainsResponse(
        search_identifier=raw["identifier"],
        complete=raw["complete"],
        expiration_time_left=raw["expiration_time_left"],
        results=results,
    )


def build_search_params(
    *,
    origin_uid: str,
    destination_uid: str,
    departure_datetime: datetime,
    passengers: list[Passenger],
) -> dict[str, Any]:
    search: dict[str, Any] = {
        "departure_datetime": _format_dt(departure_datetime),
        "route_attributes": {
            "origin_station_attributes": {"uid": origin_uid},
            "destination_station_attributes": {"uid": destination_uid},
        },
        "searches_passengers_attributes": build_passengers_attributes(passengers),
    }

    return {"search": search}
