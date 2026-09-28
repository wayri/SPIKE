# SPDX-License-Identifier: Apache-2.0
"""Launch SPIKE's local stdio MCP server from a source checkout."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.spike_core.mcp_server import serve


if __name__ == "__main__":
    serve()
