"""MCP server for groundcrew.

Start:  python -m groundcrew.mcp_server
Or:     groundcrew-mcp

Add to Claude Desktop (~/.config/claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "groundcrew": {
                "command": "groundcrew-mcp"
            }
        }
    }
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from typing import Any

from groundcrew.codec import ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore

_DEFAULT_DB = ".groundcrew/receipts.db"

try:
    import mcp.server.stdio as _mcp_stdio
    import mcp.types as _mcp_types
    from mcp.server import Server as _Server
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


def _db_path() -> str:
    return os.environ.get("GROUNDCREW_DB", _DEFAULT_DB)


def _capture_state(arguments: str) -> str:
    args = json.loads(arguments) if arguments else {}
    root = args.get("root", ".")
    verb = args.get("verb", "act")
    target = args.get("target", "")
    params = args.get("params", {})
    run_cmd = args.get("run_cmd")
    spec = ActionSpec(verb=verb, target=target, params=params)
    with Oracle(root, spec) as oracle:
        if run_cmd:
            result = subprocess.run(shlex.split(run_cmd), cwd=root, check=False)  # noqa: S603
            if result.returncode != 0:
                oracle._success = False
    receipt = oracle.record(spec)
    store = ReceiptStore(_db_path())
    store.save(receipt)
    store.close()
    return json.dumps(receipt.to_dict())


def _get_receipt(arguments: str) -> str:
    args = json.loads(arguments) if arguments else {}
    receipt_id = args.get("receipt_id", "")
    store = ReceiptStore(_db_path())
    receipt = store.get(receipt_id)
    store.close()
    if receipt is None:
        return json.dumps({"error": f"Receipt not found: {receipt_id}"})
    return json.dumps(receipt.to_dict())


def _list_receipts(arguments: str) -> str:
    store = ReceiptStore(_db_path())
    receipts = store.list_receipts()
    store.close()
    return json.dumps({"receipts": [r.to_dict() for r in receipts]})


def run_server() -> None:
    """Start the MCP server on stdio."""
    if not _HAS_MCP:
        print(
            "MCP server requires: pip install 'groundcrew[mcp]'",
            file=sys.stderr,
        )
        sys.exit(1)

    server = _Server("groundcrew")

    @server.list_tools()
    async def list_tools() -> list[_mcp_types.Tool]:
        return [
            _mcp_types.Tool(
                name="capture_state",
                description=(
                    "Capture before/after filesystem state around an action and "
                    "store a verifiable receipt. Argument is a JSON string with "
                    "keys: root, verb, target, params, run_cmd."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"arguments": {"type": "string"}},
                    "required": ["arguments"],
                },
            ),
            _mcp_types.Tool(
                name="get_receipt",
                description=(
                    "Fetch a stored receipt by ID. Argument is a JSON string with key: receipt_id."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"arguments": {"type": "string"}},
                    "required": ["arguments"],
                },
            ),
            _mcp_types.Tool(
                name="list_receipts",
                description="List all stored receipts. Argument is an (ignored) JSON string.",
                inputSchema={
                    "type": "object",
                    "properties": {"arguments": {"type": "string"}},
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[_mcp_types.TextContent]:
        raw = arguments.get("arguments", "{}")
        if name == "capture_state":
            result = _capture_state(raw)
        elif name == "get_receipt":
            result = _get_receipt(raw)
        elif name == "list_receipts":
            result = _list_receipts(raw)
        else:
            raise ValueError(f"Unknown tool: {name}")
        return [_mcp_types.TextContent(type="text", text=result)]

    import asyncio

    async def _main() -> None:
        async with _mcp_stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_main())


if __name__ == "__main__":
    run_server()
