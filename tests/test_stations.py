from saveatrain_mcp.stations import StationsRepo


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.last_pipeline = None

    def aggregate(self, pipeline):
        self.last_pipeline = pipeline
        return FakeCursor(self.docs)


class FakeDb:
    def __init__(self, search_names, stations=None, countries=None):
        self._collections = {
            "station_search_names": search_names,
            "stations": stations or FakeCollection(),
            "station_countries": countries or FakeCollection(),
        }

    def __getitem__(self, name):
        return self._collections[name]


def _repo_with(docs):
    search_names = FakeCollection(docs=docs)
    db = FakeDb(search_names)
    repo = StationsRepo.__new__(StationsRepo)
    repo._db = db  # type: ignore[attr-defined]
    return repo, search_names


async def test_search_builds_expected_pipeline():
    repo, search_names = _repo_with([])
    await repo.search("Lond")

    p = search_names.last_pipeline
    assert p is not None

    # First stage: Atlas $search with autocomplete on `name`, filtered by language_id=1 (en).
    search_stage = p[0]["$search"]
    assert search_stage["index"] == "autocomplete"
    must = search_stage["compound"]["must"]
    assert must[0]["autocomplete"]["query"] == "Lond"
    assert must[0]["autocomplete"]["path"] == "name"
    flt = search_stage["compound"]["filter"]
    assert flt[0]["equals"] == {"path": "language_id", "value": 1}

    # Lookup to stations, unwind, filter searchable.
    assert any(
        s.get("$lookup", {}).get("from") == "stations"
        and s["$lookup"]["localField"] == "station_id"
        and s["$lookup"]["foreignField"] == "id"
        for s in p
    )
    assert any(s.get("$match", {}).get("station.state") == "searchable" for s in p)

    # Lookup to station_countries via station.station_country_id -> id.
    assert any(
        s.get("$lookup", {}).get("from") == "station_countries"
        and s["$lookup"]["localField"] == "station.station_country_id"
        and s["$lookup"]["foreignField"] == "id"
        for s in p
    )

    # Final projection includes the expected keys.
    project = next(s["$project"] for s in p if "$project" in s)
    assert set(project.keys()) >= {"name", "uid", "country", "location"}
    assert project.get("_id") == 0


async def test_search_returns_projected_docs():
    docs = [
        {
            "name": "London St Pancras",
            "uid": "LSP",
            "country": "United Kingdom",
            "location": {"lat": 51.53, "lng": -0.13},
        },
        {
            "name": "Londres",
            "uid": "LDR",
            "country": "France",
            "location": {"lat": 48.8, "lng": 2.3},
        },
    ]
    repo, _ = _repo_with(docs)
    result = await repo.search("Lon")
    assert result == docs


async def test_search_respects_limit():
    repo, search_names = _repo_with([])
    await repo.search("Lon", limit=3)
    p = search_names.last_pipeline
    limit_stage = next(s["$limit"] for s in p if "$limit" in s)
    assert limit_stage == 3
