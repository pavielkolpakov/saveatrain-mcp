from datetime import datetime

from saveatrain_mcp.models import (
    Passenger,
    SearchTrainsResponse,
    build_passengers_attributes,
    build_search_params,
    parse_search_response,
)


def test_adult_passenger_maps_to_sat_format():
    passengers = [Passenger(type="adult")]
    result = build_passengers_attributes(passengers)
    assert result == {
        "0": {
            "age": None,
            "passenger_type_attributes": {"type": "Search::PassengerType::Adult"},
        }
    }


def test_youth_passenger_includes_age():
    passengers = [Passenger(type="youth", age=10)]
    result = build_passengers_attributes(passengers)
    assert result == {
        "0": {
            "age": 10,
            "passenger_type_attributes": {"type": "Search::PassengerType::Youth"},
        }
    }


def test_multiple_passengers_indexed():
    passengers = [
        Passenger(type="adult"),
        Passenger(type="youth", age=15),
        Passenger(type="senior"),
    ]
    result = build_passengers_attributes(passengers)
    assert len(result) == 3
    assert result["0"]["passenger_type_attributes"]["type"] == "Search::PassengerType::Adult"
    assert result["1"]["passenger_type_attributes"]["type"] == "Search::PassengerType::Youth"
    assert result["1"]["age"] == 15
    assert result["2"]["passenger_type_attributes"]["type"] == "Search::PassengerType::Senior"


def test_all_passenger_types():
    for ptype in ("adult", "youth", "senior", "child", "infant"):
        p = Passenger(type=ptype)
        result = build_passengers_attributes([p])
        expected_class = f"Search::PassengerType::{ptype.capitalize()}"
        assert result["0"]["passenger_type_attributes"]["type"] == expected_class


def test_build_search_params_one_way():
    params = build_search_params(
        origin_uid="SAT_OXQJY",
        destination_uid="SAT_OTWZL",
        departure_datetime=datetime(2025, 3, 12, 10, 0),
        passengers=[Passenger(type="adult")],
    )
    assert params == {
        "search": {
            "departure_datetime": "2025-03-12 10:00",
            "route_attributes": {
                "origin_station_attributes": {"uid": "SAT_OXQJY"},
                "destination_station_attributes": {"uid": "SAT_OTWZL"},
            },
            "searches_passengers_attributes": {
                "0": {
                    "age": None,
                    "passenger_type_attributes": {"type": "Search::PassengerType::Adult"},
                }
            },
        }
    }
    assert "return_departure_datetime" not in params["search"]


RAW_SEARCH_RESPONSE = {
    "identifier": "vAa4xK",
    "complete": True,
    "route": {"origin_station": {"name": "Paris"}, "destination_station": {"name": "Brussels"}},
    "departure_datetime": "2025-03-12 10:00",
    "expiration_time_left": 1800,
    "is_beginning": True,
    "is_ending": False,
    "results": [
        {
            "id": 777,
            "identifier": "830001700,830008500",
            "departure_datetime": "2025-03-12 10:25",
            "arrival_datetime": "2025-03-12 12:22",
            "duration": 117,
            "best_price": 29.0,
            "selected": False,
            "provider": {"name": "Nsi"},
            "changes_count": 0,
        },
        {
            "id": 778,
            "identifier": "830001700,830008500",
            "departure_datetime": "2025-03-12 11:25",
            "arrival_datetime": "2025-03-12 14:44",
            "duration": 199,
            "best_price": 17.7,
            "selected": False,
            "provider": {"name": "Nsi"},
            "changes_count": 2,
        },
    ],
}


def test_parse_search_response_trims():
    resp = parse_search_response(RAW_SEARCH_RESPONSE)
    assert isinstance(resp, SearchTrainsResponse)
    assert resp.search_identifier == "vAa4xK"
    assert resp.complete is True
    assert resp.expiration_time_left == 1800
    assert len(resp.results) == 2

    r0 = resp.results[0]
    assert r0.id == 777
    assert r0.departure_datetime == "2025-03-12 10:25"
    assert r0.arrival_datetime == "2025-03-12 12:22"
    assert r0.duration == 117
    assert r0.best_price == 29.0
    assert r0.changes_count == 0
    assert r0.provider == "Nsi"


def test_parse_search_response_drops_extra_fields():
    resp = parse_search_response(RAW_SEARCH_RESPONSE)
    dumped = resp.model_dump()
    assert "route" not in dumped
    assert "is_beginning" not in dumped
    assert "selected" not in dumped["results"][0]
    assert "identifier" not in dumped["results"][0]
