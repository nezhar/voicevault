"""Read-only MCP smoke check; credentials come from the environment."""

import asyncio
import os

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    url = os.environ["VOICEVAULT_MCP_URL"]
    token = os.environ["VOICEVAULT_PAT"]
    async with (
        httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http,
        streamable_http_client(url, http_client=http) as (read, write, _),
        ClientSession(read, write) as client,
    ):
        await client.initialize()
        tools = await client.list_tools()
        print(f"Discovered {len(tools.tools)} tools")
        resources = await client.list_resource_templates()
        print(f"Discovered {len(resources.resourceTemplates)} resource templates")
        result = await client.call_tool("list_entries", {"per_page": 1})
        if result.isError:
            raise RuntimeError(
                "MCP list_entries failed; check PAT permissions and server logs",
            )
        print(f"Visible entries: {result.structuredContent['total']}")


if __name__ == "__main__":
    asyncio.run(main())
