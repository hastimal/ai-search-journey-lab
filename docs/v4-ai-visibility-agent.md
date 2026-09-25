# AI Visibility Agent [V4]: Read-Only Historical Intelligence

> **Milestone 6 & 7 Architectural Article**<br>
> An autonomous conversational analytics agent built on **Google ADK** (Agent Development Kit) and the **Model Context Protocol (MCP)** for strictly read-only querying, longitudinal trend analysis, competitive brand benchmarking, citation audits, and fan-out query gap analysis over persisted BigQuery visibility history.

---

## 1. Overview & Architecture

The V4 AI Visibility Agent provides natural-language business intelligence over historical AI search scans without writing any data or executing live web/places searches.

```text
User Question ──▶ ADK Agent (Gemini) ──▶ Stdio MCP Toolset ──▶ local MCP Server ──▶ Read-Only BigQuery Analytics
```

### Key Architectural Pillars

- **Strictly Read-Only Guarantee**: V4 never executes new Google Places API calls, web searches, or BigQuery write operations. It acts purely as an analytical lens over existing V3 scan history.
- **Discovery-First Grounding**: For broad questions or questions without a brand/date range, the agent uses `get_available_history` to discover available history before analysis.
- **Protocol-Isolated MCP Server**: The analytical database tools run in an isolated local MCP server process communicating over JSON-RPC stdio.
- **Dual Invocation Modes**: Fully accessible via the **AI Visibility Agent [V4]** interactive chat tab or standalone command-line script (`scripts/demo_visibility_agent_v4.py`).

### Supported MCP Tools

1. `get_available_history`: Discovers persisted scan counts, date ranges, unique brands, and recent scan windows.
2. `get_visibility_summary`: Aggregates brand mention rates, recommendation rates, and citation rates for a requested brand/date window.
3. `get_brand_trend`: Computes historical visibility metrics across available scan dates.
4. `compare_brands`: Performs side-by-side comparison of mention, recommendation, and citation metrics between a target brand and its competitors.
5. `analyze_citations`: Performs citation-domain analysis across observed search journeys.
6. `find_fanout_gaps`: Identifies fan-out queries where a brand is missing from observed results.

---

## 2. Run and Inspect It Yourself

You can query historical visibility intelligence through the Streamlit UI or directly via the CLI demo script.

### Local Setup & Launch

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Launch the Streamlit Journey Inspector
streamlit run src/ai_search_journey/app.py
```

*(Or run the CLI demo: `python scripts/demo_visibility_agent_v4.py`)*

### Interactive Workflow in UI

1. Open the **AI Visibility Agent [V4]** tab in the Streamlit application.
2. Ensure BigQuery persistence is configured (or use existing historical scan records).
3. In the chat interface, run the following sample prompts.

### Prompt 1: Broad History & Visibility Summary

Ask the agent to inspect historical scan coverage and provide an overarching visibility summary:

```text
Give me a visibility summary for the available history. Use the most recent available scan window.
```

The agent uses the appropriate read-only MCP tools to analyze available history and summarize total scans, scan date windows, mention rates, and top recommended brands.

### Prompt 2: Competitive Brand Comparison

Ask the agent to benchmark a specific target brand against its competitors. Use a `brand_id` returned by `get_available_history` (e.g. `pullman_coffee` if present in your historical scan records):

```text
Compare pullman_coffee against its competitors for the most recent available scan window.
```

The agent uses the appropriate read-only MCP tools to return a comparative breakdown of recommendation rates, mention counts, and citation metrics.

---

## 3. Optional BigQuery Verification Commands

> [!NOTE]
> **Verification of V3 History Only**: V4 is strictly read-only and never writes to BigQuery. The commands below allow you to independently verify the underlying V3 scan records that V4 reads and analyzes.

Both verification queries include the required `started_at` partition filter:

### 1. Per-Brand Visibility Scores
Verifies the aggregated brand observations stored in `brand_observations`:

```bash
bq --project_id=ai-search-journey-lab query --use_legacy_sql=false --format=pretty '
SELECT
  brand_id,
  COUNT(DISTINCT scan_id) AS total_scans,
  ROUND(100 * AVG(CAST(mentioned AS INT64)), 1) AS mention_rate_pct,
  ROUND(100 * AVG(CAST(recommended AS INT64)), 1) AS recommendation_rate_pct,
  ROUND(100 * AVG(CAST(cited AS INT64)), 1) AS citation_rate_pct,
  MAX(started_at) AS latest_scan_at
FROM `ai-search-journey-lab.ai_search_journey_v3.brand_observations`
WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
GROUP BY brand_id
ORDER BY citation_rate_pct DESC, mention_rate_pct DESC, total_scans DESC;
'
```

### 2. Recent Persisted Visibility Scans
Verifies the scan execution history in `visibility_scans`:

```bash
bq --project_id=ai-search-journey-lab query --use_legacy_sql=false --format=pretty '
SELECT
  scan_id,
  started_at,
  brand_id,
  brand_name_snapshot,
  prompt_text_snapshot
FROM `ai-search-journey-lab.ai_search_journey_v3.visibility_scans`
WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
ORDER BY started_at DESC
LIMIT 10;
'
```

*(Note: Replace `ai-search-journey-lab` and `ai-search-journey-lab.ai_search_journey_v3` with your project and dataset ID if using custom configurations).*
