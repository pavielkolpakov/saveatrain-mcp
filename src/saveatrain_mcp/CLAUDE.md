# `saveatrain_mcp` package - working notes

Seven modules, each does one thing. Below: contract + invariants for each.
Update this file when adding/removing modules or changing public surface.

## `config.py` - `Settings`
- `pydantic-settings` `BaseSettings`. Loads from env, then `.env` (path overridable via `SAT_MCP_ENV_FILE`).
- **Required:** `SAT_API_BASE_URL` (HttpUrl), `SAT_AGENT_EMAIL`, `SAT_AGENT_TOKEN` (SecretStr), `SAT_FORWARDED_FOR`, `MONGO_URI`.
- **Optional:** `MONGO_DB` (default `"sat"`), `HOST` (default `"127.0.0.1"`), `PORT` (default `8000`).
- Construction with missing required vars raises `ValidationError` listing all of them - tested in `tests/test_config.py`. Don't add lazy/default fallbacks for required vars.
- Case-insensitive env lookup. `extra="ignore"` so other env vars don't break.

## `errors.py` - typed SAT exceptions
Hierarchy:
```
SATError
├── SATAuthError       401/403 (bad token, expired, IP not whitelisted)
├── SATNotFoundError   404
├── SATValidationError 422 (reserved; tools get structured data instead)
├── SATUpstreamError   5xx
└── SATTimeoutError    httpx.TimeoutException
```
All consumers should catch these by base class (`SATError`) when generic, or specific class when reacting differently. Add new subclasses here, never inline new exception types in clients.

## `sat_client.py` - `SATClient`
- Two `httpx.AsyncClient`s under the hood: one carries default auth headers for `/api/*`, one is bare for `/healthz` (unauthenticated upstream).
- Construct with explicit kwargs (`base_url`, `agent_email`, `agent_token`, `forwarded_for`, optional `transport` for tests). Don't pass `Settings` directly - keeps the unit tests config-free.
- `await client.request(method, path, **httpx_kwargs)` - returns dict. Error mapping:
  | status | behavior |
  |--------|----------|
  | 2xx | parsed JSON (or `{}` on empty body) |
  | 422 | `{"ok": False, "error": {"type": "validation", "status": 422, "details": <body>}}` |
  | 401/403 | raise `SATAuthError` |
  | 404 | raise `SATNotFoundError` |
  | other 4xx | raise `SATUpstreamError` (unexpected) |
  | 5xx | raise `SATUpstreamError` |
  | timeout | raise `SATTimeoutError` |
- `await client.healthz()` - raises `SATUpstreamError` / `SATTimeoutError` on non-2xx or timeout.
- **No retries.** Searches are non-idempotent at the booking layer; silent retry is unsafe.
- Timeouts: `connect=5, read=30, write=10, pool=5`. SAT search calls can be slow because they fan out to rail providers.
- Always use as `async with` or call `await client.aclose()` - leaking connections will show up as warnings under pytest.

## `stations.py` - `StationsRepo`
- Atlas Search pipeline **mirrored from** `../sat-client-app/src/api/controllers/autocomplete.controller.ts`. If that frontend changes shape, update here in lockstep.
- Collections used (DB defaults to `sat`):
  - `station_search_names` (per-language translations + Atlas Search index `autocomplete`)
  - `stations` (joined via `station_id` → `id`, filtered `state == "searchable"`)
  - `station_countries` (joined via `station.station_country_id` → `id`, preserves null - some stations may not have country)
- Projection returned: `{name, uid, country, location}` (`_id` stripped).
- Default `lang="en"` (language_id=1). `LANGUAGE_MAP` covers the same languages as the frontend; add new ones there if needed.
- **Atlas Search is required.** Self-hosted Mongo without Atlas Search will not work - the `$search` stage is provider-specific.
- `ping()` runs `db.command("ping")` - cheap, used at startup.

## `models.py` - pydantic I/O models + builders
- `Passenger(type, age?)` - input model for search. `type` is `Literal["adult","youth","senior","child","infant"]`.
- `TrainResult`, `SearchTrainsResponse` - output models for `search_trains` (trims raw SAT response).
- `build_passengers_attributes(passengers)` - maps `Passenger` list to SAT's nested `searches_passengers_attributes` format.
- `build_search_params(...)` - builds the full `POST /api/searches` JSON body. Formats `datetime` to `"%Y-%m-%d %H:%M"`.
- `parse_search_response(raw)` - trims SAT search response to `SearchTrainsResponse` (drops route, pagination flags, per-result `selected`/`identifier`).

## `server.py` - FastMCP wiring + tools
- `mcp = FastMCP("saveatrain-mcp", lifespan=lifespan)` - module-level singleton.
- `lifespan(app)` (async context manager) owns the SAT client + stations repo, calls `startup_check`, yields a dict context, closes both on shutdown.
- **`startup_check(sat, stations)` is the testable seam** - pings Mongo first (cheaper), then SAT `/healthz`. Tests inject fakes; don't add startup work in the lifespan body without also exposing it here.
- `_get_sat(ctx)` / `_get_stations(ctx)` - typed helpers to pull deps from `ctx.lifespan_context`.
- **Tools** (all registered on `mcp`):
  - `ping()` - smoke test, returns `"ok"`.
  - `search_stations(query, ctx, limit=10, lang="en")` - Mongo autocomplete via `StationsRepo`.
  - `search_trains(origin_uid, destination_uid, departure_datetime, passengers, ctx)` - POST `/api/searches`, one-way only, returns trimmed `SearchTrainsResponse`.
  - `get_sub_routes(search_identifier, result_id, ctx)` - GET sub_routes, passes through full response.
  - `get_tariff_conditions(search_identifier, result_id, result_fare_id, ctx)` - GET tariff_conditions, passes through full response.
- **Error handling in tools:** known `SATError` subclasses caught and returned as `{"ok": False, "error": "..."}`. `search_stations` catches all exceptions (Mongo errors aren't `SATError`). Unknown exceptions propagate.

## `__main__.py` - CLI
- Single entry point `saveatrain-mcp` (declared in `pyproject.toml`).
- `--http` switches to HTTP transport (default stdio). `--host/--port` only meaningful with `--http`.
- `--host` and `--port` default to `HOST`/`PORT` env vars (falling back to `127.0.0.1`/`8000`). This lets Docker and Railway set bind address via env without CLI flags.
- Don't add config reading here - it's done lazily inside `lifespan()` so missing env doesn't crash before FastMCP's logging is up.
