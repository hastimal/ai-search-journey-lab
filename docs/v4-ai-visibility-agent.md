# AI Visibility Agent [V4]

The V4 AI Visibility Agent is a read-only analytics orchestrator built on **Google ADK** and the **Model Context Protocol (MCP)**. It answers questions about historical brand visibility using strictly read-only analytics data sourced from V3 scans in BigQuery.

## Architecture

The V4 implementation leverages an isolated local MCP server and an ADK orchestration agent:
1. **MCP Server (`src/ai_search_journey/visibility/mcp_server.py`)**: Uses `mcp.server.mcpserver.MCPServer` to expose 5 read-only tools. It safely queries the BigQuery database without any write capabilities or raw SQL.
2. **ADK Agent (`src/ai_search_journey/visibility/v4_agent.py`)**: A native `google.adk.Agent` configured with an `MCPToolset` that communicates via stdio to the MCP server process.

## Strict Boundaries
- **No Write Operations**: The V4 Analytics Foundation exclusively reads from the BigQuery tables.
- **Isolated from V1/V2/V3**: V4 does not execute new Google Places or Search API calls.
- **No Hallucination**: The agent's ADK instructions strictly prohibit inventing metrics, scans, or dates, and require the answer to explicitly state the applied date range.

## Supported MCP Tools
- `get_available_history`: Discovers persisted scan count, date bounds, brand IDs, and recent scan windows.
- `get_visibility_summary`: Aggregates mention/recommendation rates.
- `get_brand_trend`: Chronological data points.
- `compare_brands`: Direct competitor metrics comparison.
- `analyze_citations`: Analyzes cited domains.
- `find_fanout_gaps`: Identifies long-tail queries missing the brand.
