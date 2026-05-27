# Save a Train MCP Server

## Overview
MCP server wrapping the Save a Train (SAT) vendor API so LLM agents can search trains via natural language. v1 is read-only: resolve stations from the SAT autocomplete Mongo, search outbound/return results, and drill into legs/fares for a chosen result. No booking, no payments.

## MVP Features
- `search_stations(query, limit?)` - autocomplete against Mongo, returns station UID + display info
- `search_trains(origin_uid, destination_uid, departure_datetime, return_datetime?, passengers[])` - POST `/api/searches`, returns search identifier + result list
- `get_sub_routes(search_identifier, result_id)` - GET `.../sub_routes`, returns legs/transfers/fares
- `get_tariff_conditions(search_identifier, result_id, result_fare_id)` - GET `.../tariff_conditions/{id}`, returns cancel/exchange rules
- Both transports: stdio (Claude Desktop / Code) and HTTP/SSE (remote)

## Out of Scope (v1)
- Booking flow (`confirm_selection`, `bookings`, `confirm`)
- Payments, vouchers, cancellations, fare/station changes
- Inbound pagination, popular routes, currencies, reduction codes
- Order retrieval (`order_info`)
- Per-request auth / multi-tenant (env vars only for now)
- Caching, retries beyond basic, observability

## Tech Stack
| Layer       | Choice                              | Reason |
|-------------|-------------------------------------|--------|
| Language    | Python 3.12.2+                      | Required by FastMCP 3.x |
| MCP server  | FastMCP 3.x (`fastmcp>=3.0,<4`)     | Both stdio + HTTP from one codebase; newer than `mcp[cli]` |
| HTTP client | httpx (async)                       | Async-friendly, plays well w/ FastMCP |
| DB driver   | motor (async MongoDB)               | Async to match httpx |
| Config      | pydantic-settings + `.env`          | Env-based secrets, typed |
| Validation  | pydantic models for tool I/O        | Schema-driven, gives MCP clients clear contracts |
| Packaging   | uv + pyproject.toml                 | Fast, modern Python tooling |
| Lint/format | ruff                                | One tool, fast |

## Architecture

```
┌──────────────┐    stdio / HTTP    ┌─────────────────────┐
│  MCP client  │ ─────────────────► │  FastMCP server     │
│ (Claude etc) │                    │  (saveatrain-mcp)   │
└──────────────┘                    └──────┬──────────────┘
                                           │
                          ┌────────────────┼────────────────┐
                          ▼                                 ▼
                ┌──────────────────┐              ┌──────────────────┐
                │  SAT vendor API  │              │   MongoDB        │
                │  /api/*       │              │  stations coll.  │
                │  (httpx + token) │              │  (motor)         │
                └──────────────────┘              └──────────────────┘
```

Layout:
```
saveatrain-mcp/
  src/saveatrain_mcp/
    __init__.py
    server.py          # FastMCP app + tool registration
    config.py          # pydantic-settings (env)
    sat_client.py      # httpx wrapper, auth headers, error mapping
    stations.py        # motor Mongo client + query
    tools/
      search_stations.py
      search_trains.py
      get_sub_routes.py
      get_tariff_conditions.py
    models.py          # pydantic I/O models
  tests/
  pyproject.toml
  .env.example
  README.md
```

Required env:
- `SAT_API_BASE_URL` (e.g. `https://vendor.saveatrain.com`)
- `SAT_AGENT_EMAIL`, `SAT_AGENT_TOKEN`
- `SAT_FORWARDED_FOR` (server's outbound IP, must be whitelisted)
- `MONGO_URI`, `MONGO_DB` (default `sat`)
- Optional: `SAT_MCP_ENV_FILE` to override `.env` location

Collections (hard-coded, schema mirrored from `sat-client-app`): `station_search_names`, `stations`, `station_countries`.

## Implementation Phases

### Phase 1 - Foundation (locked decisions)
- [ ] `uv init --package` (src layout), Python 3.12.2+, pyproject.toml w/ ruff (`E,F,I,B,UP,SIM,N`, line-length 100)
- [ ] Single console entry point `saveatrain-mcp`; `--http` flag toggles transport (stdio default), `--host/--port` for HTTP
- [ ] pydantic-settings config loader + `.env.example`; hard-fail at startup if any required var missing
- [ ] `errors.py`: typed exceptions (`SATAuthError`, `SATNotFoundError`, `SATValidationError`, `SATUpstreamError`, `SATTimeoutError`)
- [ ] `sat_client.py`: singleton `httpx.AsyncClient` w/ default auth headers, `Timeout(connect=5, read=30, write=10, pool=5)`, zero retries
  - Error mapping: 2xx → payload; 422 → `{ok: false, error: {...}}` (data, agent-correctable); 401/403 → `SATAuthError`; 404 → `SATNotFoundError`; 5xx → `SATUpstreamError`; timeout → `SATTimeoutError`
  - `healthz()` calls unauthenticated `GET /healthz`
- [ ] `stations.py`: motor client, Atlas Search aggregation pipeline mirrored from `sat-client-app/src/api/controllers/autocomplete.controller.ts`, with extra `$lookup` to `station_countries` (via `station_country_id`). Default `lang="en"` (language_id=1), hard-coded in Phase 1.
- [ ] FastMCP 3.x skeleton (`server.py`): `@asynccontextmanager` lifespan owns httpx + motor clients; startup pings Mongo (`db.command("ping")`) + SAT `/healthz`, fails fast on either
- [ ] Stub `ping` tool returning `"ok"` for end-to-end verification via MCP Inspector / Claude Desktop

### Phase 2 - Core Tools
- [x] `search_stations` tool + pydantic schema; returns `[{uid, name, country, ...}]`
- [x] `search_trains` tool: build `search[...]` nested params, POST `/api/searches`, return identifier + condensed results
- [x] `get_sub_routes` tool: GET, return legs/transfers/fares
- [x] `get_tariff_conditions` tool
- [x] Unit tests w/ httpx mock + Mongo test double

### Phase 3 - Polish & Launch
- [ ] README: install, env setup, Claude Desktop config snippet, HTTP deploy notes
- [ ] Dockerfile for HTTP deploy
- [ ] Manual smoke test against staging SAT API
- [ ] Tag v0.1.0

## Open Questions
- Exact Mongo schema for stations - field names for name/country, multilingual handling, index strategy?
- Does `X-Forwarded-For` need to be the MCP server's IP, or can it pass through the client's? (Affects HTTP transport deployability)
- For HTTP transport: who hosts it, and is single shared agent token acceptable until per-request auth lands?
- Response trimming: raw SAT result list can be large; do we cap/summarize per call or return full payload?
- Search expiration (~30 min) - should the server cache `search_identifier` -> created_at to warn the agent, or leave it to the caller?
