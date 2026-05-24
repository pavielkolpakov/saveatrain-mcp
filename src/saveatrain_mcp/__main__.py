from __future__ import annotations

import argparse

from .server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="saveatrain-mcp")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve via HTTP/SSE instead of stdio (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
