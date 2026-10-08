from mcp_client import create_incident

result = create_incident(
    short_description="LangGraph MCP integration test",
    description=(
        "Testing the connection from the LangGraph agent "
        "to the ServiceNow PDI through MCP."
    ),
    priority="P4",
)

print("\nMCP RESULT")
print("=" * 60)
print(result)