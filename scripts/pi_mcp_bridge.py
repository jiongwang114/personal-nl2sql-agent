import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the DataEngineer MCP server and emit one JSON response")
    parser.add_argument("--datasource", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--arguments", default="{}")
    parser.add_argument("--config", default="")
    return parser.parse_args()


def decode_result(result: Any) -> dict[str, Any]:
    if result.isError:
        return {"success": 0, "error": "MCP tool returned an error", "result": None}
    for content in result.content:
        text = getattr(content, "text", None)
        if not isinstance(text, str):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {"success": 0, "error": "MCP tool returned no JSON object", "result": None}


async def call_tool(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    server_args = [
        "-m",
        "dataengineer.mcp_server",
        "--datasource",
        args.datasource,
        "--transport",
        "stdio",
    ]
    if args.config:
        server_args.extend(["--config", args.config])
    parameters = StdioServerParameters(command=sys.executable, args=server_args, cwd=str(project_root))
    tool_arguments = json.loads(args.arguments)
    if not isinstance(tool_arguments, dict):
        raise ValueError("--arguments must decode to a JSON object")

    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(args.tool, tool_arguments)
            return decode_result(result)


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(call_tool(args))
    except Exception as exc:
        result = {"success": 0, "error": str(exc), "result": None}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("success") == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
