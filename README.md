# saveatrain-mcp

MCP server wrapping the [Save a Train](https://www.saveatrain.com) vendor API. Lets LLM agents search European train connections via natural language. Read-only v1 - no booking or payments.

## Tools

| Tool | Description |
|------|-------------|
| `ping` | Health check - returns `"ok"` |
| `search_stations(query, limit?, lang?)` | Autocomplete station names via MongoDB Atlas Search. Returns `uid`, name, country, location. |
| `search_trains(origin_uid, destination_uid, departure_datetime, passengers, return_datetime?)` | Search connections. Returns search identifier + results with times, duration, price, provider. |
| `get_sub_routes(search_identifier, result_id)` | Detailed legs, transfers, and fares for a search result. |
| `get_tariff_conditions(search_identifier, result_id, result_fare_id)` | Cancellation and exchange rules for a specific fare. |

## Prerequisites

- Python 3.12.2+
- [uv](https://docs.astral.sh/uv/)
- MongoDB Atlas with Atlas Search index `autocomplete` on `station_search_names.name`
- SAT vendor API credentials (agent email + token, whitelisted IP)

## Install

```bash
uv sync
cp .env.example .env  # fill in values
```

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SAT_API_BASE_URL` | yes | - | SAT vendor API base URL |
| `SAT_AGENT_EMAIL` | yes | - | Agent email for SAT auth |
| `SAT_AGENT_TOKEN` | yes | - | Agent token for SAT auth |
| `SAT_FORWARDED_FOR` | yes | - | Server's outbound IP (whitelisted by SAT) |
| `MONGO_URI` | yes | - | MongoDB Atlas connection string |
| `MONGO_DB` | no | `sat` | MongoDB database name |
| `HOST` | no | `127.0.0.1` | Bind address for HTTP mode |
| `PORT` | no | `8000` | Bind port for HTTP mode |
| `SAT_MCP_ENV_FILE` | no | `.env` | Override `.env` file location |

## Run

stdio (Claude Desktop / Claude Code):
```bash
uv run saveatrain-mcp
```

HTTP/SSE:
```bash
uv run saveatrain-mcp --http
```

Override host/port via env vars or CLI flags:
```bash
uv run saveatrain-mcp --http --host 0.0.0.0 --port 3000
```

The server pings MongoDB and SAT `/healthz` at startup and exits non-zero if either is unreachable.

## Claude Desktop config

```jsonc
{
  "mcpServers": {
    "saveatrain": {
      "command": "uv",
      "args": ["--directory", "/abs/path/to/saveatrain-mcp", "run", "saveatrain-mcp"],
      "env": {
        "SAT_API_BASE_URL": "https://vendor.saveatrain.com",
        "SAT_AGENT_EMAIL": "...",
        "SAT_AGENT_TOKEN": "...",
        "SAT_FORWARDED_FOR": "...",
        "MONGO_URI": "...",
        "MONGO_DB": "sat"
      }
    }
  }
}
```

## Docker

Build:
```bash
docker build -t saveatrain-mcp .
```

Run:
```bash
docker run --rm \
  -e SAT_API_BASE_URL=https://vendor.saveatrain.com \
  -e SAT_AGENT_EMAIL=... \
  -e SAT_AGENT_TOKEN=... \
  -e SAT_FORWARDED_FOR=... \
  -e MONGO_URI=... \
  -p 8000:8000 \
  saveatrain-mcp
```

The image binds to `0.0.0.0:8000` by default. Override with `HOST` and `PORT` env vars.

## Deploy to Railway

1. Push the repo to GitHub.
2. Create a new Railway project and connect the repo.
3. Railway auto-detects the `Dockerfile` via `railway.toml`.
4. Add all required env vars in the Railway dashboard (Settings > Variables). Railway sets `PORT` automatically.
5. Deploy. The health check runs at startup - check logs if the service fails to start.

## Test

```bash
uv run pytest
```

## License

Proprietary.
