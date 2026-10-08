import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():

    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server/server.py"],
    )

    async with stdio_client(server_params) as (read, write):

        async with ClientSession(read, write) as session:

            # Initialize MCP connection
            await session.initialize()

            # -------------------------------------------------
            # 1. List available tools
            # -------------------------------------------------

            tools = await session.list_tools()

            print("\nAvailable MCP tools:\n")

            for tool in tools.tools:
                print(f"- {tool.name}")

            # -------------------------------------------------
            # 2. Call create_incident
            # -------------------------------------------------

            print("\nCalling create_incident...\n")

            result = await session.call_tool(
                "create_incident",
                {
                    "short_description":
                        "MCP Test - MID Server connectivity issue",

                    "description":
                        "This is a test incident created through "
                        "the MCP server for the ITOM AI Assistant project.",

                    "priority": "P4"
                }
            )

            print("Tool result:\n")
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
