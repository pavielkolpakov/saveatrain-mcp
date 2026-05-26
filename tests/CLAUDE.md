# `tests/` - working notes

Pytest with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed). Run via `uv run pytest`.

## Conventions
- **Integration-style.** Tests hit public interfaces only. No mocking of internal collaborators - if a test breaks under a refactor that didn't change behavior, the test is wrong.
- **httpx:** use `httpx.MockTransport(handler)` and inject it into `SATClient(transport=...)`. Real client, fake transport - exercises actual httpx request/response code paths.
- **Motor:** use the in-file `FakeCollection` / `FakeDb` / `FakeCursor` helpers in `test_stations.py`. We don't pull `mongomock` because Atlas Search semantics aren't reproducible anywhere local; the pipeline structure is the contract worth pinning. Atlas Search behavior is verified manually against staging.
- **Settings:** always clear env via `monkeypatch.delenv` and point `SAT_MCP_ENV_FILE` at a non-existent path so a stray `.env` in CWD doesn't leak in.
- **FastMCP:** test tool functions directly with `FakeContext` (duck-typed `lifespan_context` dict). Don't spin up the server in unit tests.

## Files
| file | covers |
|------|--------|
| `test_config.py` | Settings hard-fail + happy path |
| `test_sat_client.py` | full error-mapping table, auth headers, healthz, Phase 2 endpoint paths |
| `test_stations.py` | Atlas Search pipeline shape + projection + limit + lang |
| `test_server.py` | startup_check, ping, search_stations, search_trains, get_sub_routes, get_tariff_conditions |
| `test_models.py` | passenger mapping, search param building, response parsing/trimming |

## When adding tests
- New SAT tool → integration test with `MockTransport` returning a realistic payload; assert tool output shape.
- New Mongo query → fake collection captures the pipeline; assert the stages you actually care about (don't over-pin on irrelevant ordering).
- New startup work → extend `startup_check`'s signature + tests rather than wedging logic into the lifespan body.

Update this file if conventions change (e.g., we adopt `mongomock`, switch async modes, add fixtures).
