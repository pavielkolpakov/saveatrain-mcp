from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

# Mirrors sat-client-app/src/api/services/mongodb.service.ts
LANGUAGE_MAP = {
    "en": 1,
    "fr": 4,
    "it": 12,
    "de": 13,
    "es": 3,
    "nl": 2,
    "pl": 6,
    "ru": 10,
    "tr": 9,
    "ja": 11,
    "in": 8,
    "ae": 7,
    "zh-CN": 5,
}


class StationsRepo:
    def __init__(self, mongo_uri: str, db_name: str = "sat") -> None:
        self._client = AsyncIOMotorClient(mongo_uri)
        self._db = self._client[db_name]

    async def ping(self) -> None:
        await self._db.command("ping")

    async def aclose(self) -> None:
        self._client.close()

    async def search(self, query: str, limit: int = 10, lang: str = "en") -> list[dict[str, Any]]:
        language_id = LANGUAGE_MAP[lang]
        pipeline: list[dict[str, Any]] = [
            {
                "$search": {
                    "index": "autocomplete",
                    "compound": {
                        "must": [
                            {
                                "autocomplete": {
                                    "query": query,
                                    "path": "name",
                                    "tokenOrder": "sequential",
                                }
                            }
                        ],
                        "filter": [{"equals": {"path": "language_id", "value": language_id}}],
                    },
                }
            },
            {
                "$lookup": {
                    "from": "stations",
                    "localField": "station_id",
                    "foreignField": "id",
                    "as": "station",
                }
            },
            {"$unwind": "$station"},
            {"$match": {"station.state": "searchable"}},
            {
                "$lookup": {
                    "from": "station_countries",
                    "localField": "station.station_country_id",
                    "foreignField": "id",
                    "as": "country",
                }
            },
            {"$unwind": {"path": "$country", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"weight": -1}},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "name": "$name",
                    "uid": "$station.uid",
                    "country": "$country.name",
                    "location": "$station.location",
                }
            },
        ]
        cursor = self._db["station_search_names"].aggregate(pipeline)
        return await cursor.to_list(length=limit)
