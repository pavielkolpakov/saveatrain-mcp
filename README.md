# saveatrain-mcp

MCP server wrapping the Save a Train vendor API. Phase 1: foundation only - config, SAT client, Mongo stations repo, FastMCP skeleton with a `ping` tool. Real tools land in Phase 2.

## Install

```bash
uv sync
cp .env.example .env  # fill in values
```

Requires Python 3.12.2+.

## Run

stdio (default - for Claude Desktop / Claude Code):
```bash
uv run saveatrain-mcp
```

HTTP/SSE:
```bash
uv run saveatrain-mcp --http --host 127.0.0.1 --port 8000
```

Server pings Mongo and SAT `/healthz` at startup and exits non-zero if either is unreachable.

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

## Test

```bash
uv run pytest
```
