# AI Visibility Agent [V4]

## Architecture and Boundary

The V4 AI Visibility Agent acts as a secure, read-only analytics foundation layered on top of historical V3 AI Visibility scans stored in BigQuery.

```ascii
+-----------------------+      +-----------------------+
|  V3 Scan Engine       |      |  V4 Conversational    |
|  (Generates Data)     |      |  Agent (Reads Data)   |
+-----------+-----------+      +-----------+-----------+
            |                              |
            v                              v
+-----------+-----------+      +-----------+-----------+
| BigQuery Visibility   |      | VisibilityAnalytics   |
| Repository (Writes)   |<-----| Repository (Read Only)|
+-----------------------+      +-----------------------+
```

### Strict Boundaries
*   **No New Searches**: V4 will *never* run Google Places, Google Search grounding, query fan-out, or a new V1/V2/V3 journey. It exclusively analyzes persisted data.
*   **Read-Only Guarantee**: V4 has absolutely no write operations. It prohibits INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, and arbitrary user-entered SQL.
*   **Parameterized Queries Only**: All analysis relies on a fixed allowlist of safe, parameterized BigQuery methods.

## Proposed Agent Capabilities

The V4 agent exposes five core analytical tools (MCP Tool contracts) to answer user questions about historical visibility:

1.  **Visibility Summary** (`get_visibility_summary`):
    *   Aggregates high-level metrics (mention rate, recommendation rate, citation rate) for a brand over a specific time window.
2.  **Brand Trend** (`get_brand_trend`):
    *   Returns chronological data points showing how a brand's visibility metrics have changed over time, highlighting increases or decreases in share of voice.
3.  **Competitor Comparison** (`compare_brands`):
    *   Directly compares the visibility metrics of multiple brands side-by-side, answering "Who is performing better: Brand A or Brand B?".
4.  **Citation / Domain Analysis** (`analyze_citations`):
    *   Analyzes which domains and source types are most frequently cited when a brand is mentioned or recommended, identifying key referral sources.
5.  **Fan-out Coverage Gaps** (`find_fanout_gaps`):
    *   Examines query fan-outs to identify specific long-tail queries or sub-tasks where the brand was *not* found, highlighting areas for optimization.
