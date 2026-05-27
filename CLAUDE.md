# saveatrain-mcp - working notes for Claude

MCP server wrapping the Save a Train (SAT) vendor API. Python 3.12.2+, FastMCP 3.x, httpx, motor (MongoDB Atlas). Read-only v1: station autocomplete + train search drill-down. No booking/payment.

See `PLAN.md` for scope, phases, and locked decisions. See `mcp.md` for the upstream API reference (auth headers, endpoints, payload shapes).

## Status
- **Phase 1 (Foundation): done.** Config, error mapping, SAT client, stations repo, FastMCP skeleton with `ping` tool.
- **Phase 2 (Tools): done.** `search_stations`, `search_trains`, `get_sub_routes`, `get_tariff_conditions` + pydantic models. 45 tests.
- **Phase 3 (Polish & Launch): done.** README rewrite, Dockerfile (multi-stage), railway.toml, .dockerignore, HOST/PORT env vars, v0.1.0 tag.

## Layout
```
src/saveatrain_mcp/
  __init__.py       re-exports mcp
  __main__.py       argparse entry point (stdio | --http), HOST/PORT from env
  config.py         pydantic-settings Settings (hard-fail)
  errors.py         typed SAT exceptions
  models.py         pydantic I/O models + SAT param builders
  sat_client.py     httpx wrapper + error mapping + /healthz
  stations.py       motor + Atlas Search aggregation pipeline
  server.py         FastMCP instance, lifespan, startup_check, 5 tools
tests/              pytest, asyncio_mode=auto
Dockerfile          multi-stage (uv build + slim runtime)
railway.toml        Railway deploy config
```

Each subdir has its own `CLAUDE.md` with details specific to that module.

## How to work in this repo
- **Tooling:** `uv` (not pip). `uv sync` to install, `uv run pytest`, `uv run ruff check`, `uv run ruff format`.
- **TDD:** keep it. Tests are integration-style against public interfaces (`MockTransport` for httpx, fake collections for motor). Don't mock internal collaborators.
- **Lifespan injection:** `server.py` exposes `startup_check(sat, stations)` as a pure function so it can be tested without booting FastMCP. Preserve this seam when adding new startup work.
- **Error contract:** 422 from SAT → structured `{ok: False, error: {...}}` returned as data (LLM can self-correct). Everything else 4xx/5xx raises a typed exception. Don't break this without updating `tests/test_sat_client.py`.
- **Mongo schema:** mirrored from `../sat-client-app/src/api/controllers/autocomplete.controller.ts`. If that frontend changes, update `stations.py` and its tests in lockstep.
- **`/healthz` on SAT** is unauthenticated - use the separate client in `SATClient`, never inject auth headers there.
- **`X-Forwarded-For`** is a static env var pointing to the server's outbound IP (whitelisted by SAT). Per-request pass-through is deferred.

## Keep CLAUDE.md files current
When you change a module in a way that affects how to use it, what it depends on, or its contracts (public functions, returned shapes, raised exceptions, env vars, external schemas), update the relevant `CLAUDE.md` in the same change. Specifically:

- Add/remove/rename a tool, function, or env var → update that module's `CLAUDE.md` **and** this root file's Status / Layout sections.
- Change error mapping, lifespan, or startup checks → update `src/saveatrain_mcp/CLAUDE.md` and `server.py`'s notes.
- Change the Mongo pipeline or upstream API contract → update `stations.py`'s or `sat_client.py`'s `CLAUDE.md`.
- Finish a phase → flip Status here and prune obsolete notes.

Keep entries terse. If a note no longer matches the code, delete it - stale notes are worse than missing ones.

## User context
- Date format / preferences live in `~/.claude/CLAUDE.md` (concise, no em-dashes).
- The grilling session that drove Phase 1 decisions is summarized in `PLAN.md`; details (rejected alternatives, etc.) are not reproduced - if you need them, ask.
