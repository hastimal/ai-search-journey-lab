# AI Visibility [V3]: Brand Presence & Share of Voice Analytics

> **Milestone 4 & 5 Architectural Article**<br>
> Measuring brand visibility, narrative mention rates, recommendation rates, owned citation authority, and competitive Share of Voice (SOV) across AI search journeys with optional Google Cloud BigQuery persistence.

---

## 1. Overview: AI Visibility Analytics

Traditional search visibility tracks domain rankings for static keywords. **AI Visibility** measures how prominently a brand appears inside generative AI search summaries and recommendations compared to direct competitors.

### Key Visibility Metrics

- **Brand Presence Rate**: Percentage of fan-out queries where the brand was retrieved by tool calls.
- **Narrative Mention Rate**: Frequency with which the brand is cited or mentioned in synthesis text.
- **Recommendation Rate**: Frequency with which the brand achieves a Top-3 final recommendation.
- **Owned Citation Authority**: Percentage of citations linking directly to the brand's verified website.
- **Share of Voice (SOV)**: Competitive visibility proportion normalized across all evaluated brand occurrences.

### Dual Storage Architecture

- **Session (In-Memory)**: Default mode for local development, Streamlit exploration, and public demos without database dependencies.
- **Google Cloud BigQuery (Optional)**: Partitioned, clustered historical repository enabling longitudinal trend tracking, cross-run comparisons, and analytical querying.

---

## 2. Run and Inspect It Yourself

You can run visibility scans interactively through the GUI or execute the terminal demo.

### Local Setup & Launch

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Launch the Streamlit Journey Inspector
streamlit run src/ai_search_journey/app.py
```

*(Or run the CLI demo: `python scripts/demo_visibility_v3.py`)*

### Interactive Workflow in UI

1. Run a search journey in **Search to Decision [V1]** (e.g. the Geekdom coffee shop query).
2. Switch to the **AI Visibility [V3]** tab.
3. Configure the **Target Brand** (e.g. `Kafe Krave` or `Pullman Coffee`) with optional website domain matching.
4. Select discovered competitor candidates or add custom competitors.
5. Click **🔍 Run AI Visibility Analysis**.
6. Inspect the resulting **Visibility Scorecard**, **Share of Voice Breakdown**, **Narrative Mention Analysis**, and **Citation Audit**.

---

## 3. Optional BigQuery Inspection Commands

When BigQuery persistence is enabled (configured via `BIGQUERY_PROJECT`, `BIGQUERY_DATASET`, and `bootstrap_bigquery_v3.sh --apply`), V3 persists structured scan bundles into partitioned BigQuery tables.

You can inspect the persisted visibility history using these copy/paste `bq` commands (both include the required `started_at` partition filter):

### 1. Per-Brand Visibility Scores
Aggregates scan counts, mention rates, recommendation rates, citation rates, and latest scan timestamp per brand:

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
Lists the most recent scans recorded in the fact table with scan execution metadata:

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
