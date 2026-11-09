"""python -m imessage_mcp → runs the FastMCP server over stdio (dry-run unless IMESSAGE_MCP_LIVE=1)."""

import sys

from .config import ConfigError
from .server import create_server


def main() -> None:
    try:
        server = create_server()
    except ConfigError as e:
        print(f"imessage-mcp: {e}", file=sys.stderr)
        sys.exit(2)
    server.run("stdio")


if __name__ == "__main__":
    main()
