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
        error_text = next(
            (
                content.text
                for content in result.content
                if isinstance(getattr(content, "text", None), str) and content.text.strip()
            ),
            "MCP tool returned an error",
        )
        return {"success": 0, "error": error_text, "result": None}
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


def call_registered_tool(datasource: str, tool_name: str, tool_arguments: dict[str, Any], config_path: str) -> dict[str, Any]:
    """Call a registered database tool directly when stdio omits the tool from tools/list."""
    from dataengineer.mcp_server import create_server

    server = create_server(datasource=datasource, config_path=config_path or None)
    try:
        tool_instance = next(
            (instance for instance in server.tools.values() if instance and callable(getattr(instance, tool_name, None))),
            None,
        )
        if tool_instance is None:
            return {"success": 0, "error": f"Unknown DataEngineer tool: {tool_name}", "result": None}
        return server._format_result(getattr(tool_instance, tool_name)(**tool_arguments))
    finally:
        server.close()


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
            decoded = decode_result(result)
            if decoded.get("success") != 1 and str(decoded.get("error", "")).startswith("Unknown tool:"):
                return await asyncio.to_thread(
                    call_registered_tool,
                    args.datasource,
                    args.tool,
                    tool_arguments,
                    args.config,
                )
            return decoded


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
