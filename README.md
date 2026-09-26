# AI Search Journey Lab

> A transparent reference implementation for understanding how an AI-powered search journey can move from user intent → query fan-out → retrieval → grounding → evidence → deterministic constraint evaluation → ranking → grounded recommendations.

---

> **v3.0.0 Focus — AI Visibility & Search Journey Optimization (SJO)**
> How does a local business transition from its initial **Places retrieval position** to its **final AI recommendation rank**? SJO bridges retrieval provenance with deterministic constraint evaluation, evidence coverage, transparent score breakdowns, explainable rank movement ($\Delta$), and **V3 AI Visibility analytics** (Share of Voice, brand presence, narrative mention rate, and owned citation authority).
>
> **Important Architectural Scope:**
> - **Local / Public Demos:** Run strictly in-memory (`Session only`) with zero database dependencies.
> - **Optional BigQuery History:** Historical analysis and cross-run trends can be activated by configuring Google Cloud BigQuery.
> - **Educational Reference Implementation:** Uses public Google developer technologies (Gemini API via Google GenAI SDK, Google Places API (New), Google Search Grounding, Google Maps Static API, and Google Cloud Run) to demonstrate observable, multi-step search-agent design patterns.
> - **Disclaimer:** This project does **not** recreate proprietary Google Search backend systems, Google AI Overviews, or Google AI Mode.

---

## 1. Overview

Traditional search systems map keyword queries directly to ranked lists of links:

```text
User Query ──▶ Index Lookup ──▶ Ranked Links
```

Modern AI-assisted search and discovery pipelines transform unstructured, constraint-rich natural language questions into orchestrated, multi-step search journeys:

```text
User Intent ──▶ Query Fan-Out ──▶ Multi-Source Retrieval ──▶ Grounded Evidence ──▶ Deterministic Constraints ──▶ Ranking ──▶ Grounded Recommendations
```

### Core Design Philosophy

> **"Agents reason; tools retrieve; deterministic code evaluates; evidence justifies."**

- **Gemini** analyzes user questions, parses multi-label intent, generates query fan-outs, and explains the top results.
- **Google Places API (New)** retrieves structured local entity data (names, coordinates, operating hours, ratings, types, Google Maps URLs) with full retrieval provenance.
- **Google Search Grounding** gathers real-time, qualitative web evidence, source domains, and citations.
- **Deterministic Python** normalizes candidates, evaluates hard constraints and preferences, computes proximity, tracks position lifecycles, and calculates explainable ranking scores.
- **Gemini** explains and synthesizes grounded recommendations strictly for the deterministically ranked Top 3 candidates.

---

## 2. Demo

The Journey Inspector makes the complete AI search journey visible across dedicated operational stages: **Search to Decision [V1]**, **Journey Analysis [V2]**, **AI Visibility [V3]**, and **AI Visibility Agent [V4]**.

> **Important Scope & Architecture Note:**
> - **Local & Public Demos use Session Only (In-Memory):** In-memory storage is the default mode for local development, Streamlit exploration, and public demos without cloud database setup.
> - **Optional BigQuery History:** Persistent historical analysis, cross-run analytics, and multi-journey brand tracking can be enabled separately by configuring Google Cloud BigQuery.
> - **Educational Reference Implementation:** This open-source lab teaches observable, multi-step search-agent design patterns (retrieval provenance, deterministic constraint evaluation, explainable ranking, and visibility analytics). It **does not** recreate proprietary Google Search backend systems, Google AI Overviews, or Google AI Mode.

### Stage 1: Search to Decision [V1]
*End-to-end user journey showing intent extraction, query fan-out, multi-source retrieval, constraint verification, static map preview, and grounded recommendations.*

![Search to Decision V1](assets/screenshots/v1-search-to-decision.png)

### Stage 2: Journey Analysis [V2]
*Deep-dive analysis tracking candidate retrieval provenance, transparent score breakdowns (hard points, preferences, proximity, quality), and deterministic rank movement ($\Delta$).*

![Journey Analysis V2](assets/screenshots/v2-journey-analysis.png)

### Stage 3: AI Visibility [V3] — Configuration
*Target brand configuration with optional domain/alias matching, candidate competitor selection, and custom competitor additions.*

![AI Visibility V3 Configuration](assets/screenshots/v3-visibility-configuration.png)

### Stage 3: AI Visibility [V3] — Results & Share of Voice
*Multi-metric visibility dashboard reporting Brand Presence, Narrative Mention Rate, Recommendation Rate, Owned Citation Rate, and Share of Voice (SOV) against competitors.*

![AI Visibility V3 Results](assets/screenshots/v3-visibility-results.png)

### Stage 3: AI Visibility [V3] — Interactive Dashboard
*V3 AI Visibility — configure a target and competitors, run an analysis, and persist optional BigQuery history.*

![V3 AI Visibility GUI](assets/screenshots/v3_visibility_gui.png)

### Stage 4: AI Visibility Agent [V4] — Console Interface
*V4 AI Visibility Agent — read-only conversational interface grounded in persisted BigQuery visibility history.*

![V4 AI Visibility Agent UI](assets/screenshots/v4_ai_visibility_agent_ui.png)

### Stage 4: AI Visibility Agent [V4] — Grounded Analysis
*V4 grounded analysis — Gemini uses Google ADK and MCP read-only tools to compare brands, citations, fan-out gaps, and available history.*

![V4 AI Visibility Agent Grounded Analysis](assets/screenshots/v4_ai_visibility_agent.png)

---

## 3. Capabilities Demonstrated

- **Structured Intent Extraction:** Multi-label classification (`informational`, `navigational`, `commercial`, `transactional`, `local_discovery`) with structured extraction of reference locations, categories, operating hours, group sizes, hard constraints, and preferences.
- **Dynamic Query Fan-Out:** LLM-driven query planner decomposing complex requests into targeted retrieval tasks routed to appropriate tools.
- **Multi-Source Retrieval with Provenance:**
  - **Google Places API (New):** Structured candidate discovery with 1-indexed retrieval positions, fan-out task IDs, query texts, and place IDs.
  - **Gemini + Google Search Grounding:** Dynamic grounding queries, web snippets, citations, and capture of actual executed Google Search queries.
- **Candidate Normalization & Deduplication:** Stable entity consolidation using unique Google Place IDs while preserving every retrieval occurrence across fan-out queries.
- **Evidence Aggregation & Provenance:** Unifies structured Places signals and web claims while preserving source tags (`GOOGLE PLACES`, `GOOGLE SEARCH`, `DERIVED`) and fan-out task IDs (`F1`, `F2`, `F3`, etc.).
- **Evidence & Citation Coverage:** Per-candidate ratios measuring supported constraint evidence coverage and web grounding citation coverage.
- **Deterministic Constraint Matrix:** Distinguishes `SUPPORTED`, `NOT_SATISFIED`, and `UNKNOWN` (`UNKNOWN != false`).
- **Position Lifecycle & Rank Movement Tracking:**
  - **Places Retrieval Position:** Initial 1-indexed position from Google Places retrieval.
  - **Evidence-Enriched Position:** Intermediary rank after factoring in multi-source evidence.
  - **Final Recommendation Position:** Final rank after comprehensive deterministic evaluation.
  - **Rank Movement ($\Delta$):** Quantified movement (`▲ +N`, `▼ -N`, `● Unchanged`) with deterministic movement explanations.
- **Transparent Score Breakdown:** Additive scoring model decomposing candidate scores into hard constraint points, preference points, proximity points, quality points, and penalties.
- **Visual Mapping:** Dynamic Google Maps Static API preview with ranked markers (`A`, `B`, `C`) and direct Google Maps destination links.
- **Grounded Answer Generation:** Structured synthesis with per-candidate summaries, evidence citations, match rationales, and explicit unknowns.
- **AI Visibility Analytics [V3]:** Target brand and competitor benchmarking measuring presence in retrieval, narrative mentions, top-3 recommendations, citation authority, and competitive SOV.
- **Google ADK Orchestration:** Agent-driven workflow orchestration separating reasoning from deterministic evaluation.
- **Streamlit Journey Inspector:** Transparent UI visualizing execution steps, wall-clock timing, rank movement badges, score breakdowns, constraint matrices, visibility dashboards, and developer traces.
- **Production Packaging & Deployment:** Multi-stage, non-root Docker container deployment to **Google Cloud Run** backed by **Google Secret Manager** and **Artifact Registry**.

---

## 4. Demo Scenarios

The pipeline operates on arbitrary local discovery questions without hardcoded logic.

### Scenario 1 — Work-Friendly Coffee Shop
```text
"Find a coffee shop near Geekdom San Antonio for 6 people to work together, preferably quiet, and open after 8 PM."
```
- **Extracted Intent:** Category: `coffee shop`, Reference Location: `Geekdom San Antonio`, Group Size: `6`, Open After: `20:00`, Hard Constraints: `[open after 8pm, group capacity 6]`, Preferences: `[quiet, suitable for working]`.
- **Classification:** `commercial`, `local_discovery`.
- **Fan-Out:** `[PLACES]` Find coffee shops near Geekdom, `[PLACES]` Verify evening operating hours, `[SEARCH]` Check group seating and workspace suitability, `[SEARCH]` Check quiet atmosphere.

### Scenario 2 — Student Group Dining
```text
"Find an Indian restaurant near Trinity University for 8 students, open after 9 PM, with vegetarian options."
```
- **Extracted Intent:** Category: `Indian restaurant`, Reference Location: `Trinity University`, Group Size: `8`, Open After: `21:00`, Hard Constraints: `[open after 9pm, group capacity 8, vegetarian options]`.
- **Classification:** `commercial`, `local_discovery`.

---

## 5. Architecture

```text
                                              User Question
                                                    │
                                                    ▼
                                           Gemini / Google ADK
                                                    │
                                                    ▼
                                          Dynamic Query Fan-Out
                                                    │
                                ┌───────────────────┴───────────────────┐
                                ▼                                       ▼
                       Google Places API                        Gemini +
                             (New)                       Google Search Grounding
                                │                                       │
                       Structured Local Data               Qualitative Web Evidence
                       - Operating hours                   - Grounded text
                       - Coordinates (lat/lon)             - Executed search queries
                       - Ratings & review counts           - Source domains & URLs
                       - Category / Primary type           - Text grounding citations
                       - Google Maps URLs                               │
                                │                                       │
                                └───────────────────┬───────────────────┘
                                                    │
                                                    ▼
                                        Candidate Normalization
                                        (Deduplicate on Place ID)
                                                    │
                                                    ▼
                                           Evidence Aggregation
                                         (Multi-Source Provenance)
                                                    │
                                                    ▼
                                        Deterministic Constraints
                                   (SUPPORTED / UNKNOWN / NOT_SATISFIED)
                                                    │
                                                    ▼
                                          Deterministic Ranking
                                      (Hard/Pref Weights + Proximity)
                                                    │
                    ┌───────────────────────────────┴───────────────────────────────┐
                    ▼                               ▼                               ▼
       ┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
       │   V1: Recommendations   │     │   V2: Ranking Analysis  │     │  V3: Visibility Analysis│
       ├─────────────────────────┤     ├─────────────────────────┤     ├─────────────────────────┤
       │ • Top 3 Grounded Picks  │     │ • Multi-query provenance│     │ • Target brand metrics  │
       │ • Static Map & Markers  │     │ • Score decomposition   │     │ • Competitor SOV        │
       │ • Constraint matrix     │     │ • Rank movement (Δ)     │     │ • Owned citation audit  │
       │ • Grounded answer prose │     │ • Positional lifecycle  │     │ • Mention & rec. rates  │
       └─────────────────────────┘     └─────────────────────────┘     └────────────┬────────────┘
                                                                                    │
                                                                   ┌────────────────┴────────────────┐
                                                                   ▼                                 ▼
                                                       ┌───────────────────────┐         ┌───────────────────────┐
                                                       │  Session (In-Memory)  │         │   Optional BigQuery   │
                                                       │  • Default / Local    │         │   • Long-term History │
                                                       │  • Zero Setup         │         │   • Cross-run Trends  │
                                                       └───────────────────────┘         └───────────────────────┘
```

---

## 6. Journey Inspector UI

The Journey Inspector UI makes every stage of the AI search pipeline inspectable in real-time rather than treating the model as an opaque black box:

1. **Original Question & Presets:** Quick demonstration prompts or custom inputs.
2. **Live Execution Timeline:** Wall-clock monotonic elapsed time per step with progress indicators (`✓` completed, `→` running, `○` pending, `✗` failed).
3. **Inspectable Step Expanders:**
   - **Search Grounding Details:** Distinct breakdown of planner query vs. executed Google Search queries and resolved source domains.
   - **Candidate Normalization:** Raw record count, unique places retained, and duplicates removed.
   - **Evidence Sample:** Structured Places data alongside specific Search claims and fan-out task IDs.
   - **Constraint Matrix Sample:** Multi-source constraint evaluation table.
   - **Ranking Factors:** Score breakdowns (hard constraints, preferences, proximity bonus, quality bonus).
4. **Interactive Tabs:**
   - **🎯 Recommendations & Intent:** Grounded summary, candidate cards, Static Map preview, and parsed intent.
   - **🔀 Planner Query Fan-Out:** Tool routing (`GOOGLE_PLACES` vs. `GOOGLE_SEARCH`), goals, and queries.
   - **📊 Constraint Matrix & Metrics:** Full candidate evaluation matrix.
   - **🔎 Evidence Inspector:** Deep claim-by-claim citations and source URLs.
   - **🛠️ ADK Developer Trace:** Raw execution trace log.

> **Planner Query Fan-Out vs. Executed Google Search Queries:**  
> The planner query fan-out is generated by the application's reasoning layer. Executed Google Search queries represent the queries performed by Google Search grounding as reported in the response metadata.

---

## 7. Evidence & Constraint Evaluation Model

Constraint evaluations are strictly separated into 3 explicit states:

| Status | Symbol | Meaning | Scoring Impact |
| :--- | :---: | :--- | :--- |
| **`SUPPORTED`** | `✓` | Positive evidence confirms the constraint is satisfied. | Positive points applied (+25 hard, +10 pref). |
| **`NOT_SATISFIED`** | `✗` | Explicit evidence or data shows the criterion was not met (e.g., closed at target hour). | Penalty applied (-35 hard, -10 pref). |
| **`UNKNOWN`** | `?` | Neither Places nor Search contained evidence confirming or denying the constraint. | **Neutral (0 pts). `UNKNOWN != false`.** |

### Coverage Metrics
- **Evidence Coverage:** Ratio of constraints with positive evidence (`SUPPORTED`) out of total applicable constraints:
  $$\text{Evidence Coverage} = \frac{|\text{Supported Constraints}|}{|\text{Total Constraints}|}$$
- **Citation Coverage:** Ratio of constraints supported by verified external citations (e.g. web search grounding):
  $$\text{Citation Coverage} = \frac{|\text{Constraints with Cited Sources}|}{|\text{Total Constraints}|}$$

### Sample Constraint Matrix

| Candidate | Open After 8 PM | Group Capacity (6) | Quiet Atmosphere | Work Friendly | Evidence Cov. |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Local Coffee A** | `✓ PLACES [F2]` | `✓ SEARCH [F3]` | `?` | `✓ SEARCH [F4]` | 75% |
| **Local Candidate B** | `✗ PLACES [F1]` | `?` | `?` | `?` | 0% |

### Provenance Tracking
Every evidence item maintains strict source provenance:
- **`GOOGLE PLACES`**: Derived directly from verified Google Places API attributes (e.g. `regularOpeningHours`).
- **`GOOGLE SEARCH`**: Extracted from web search grounding chunks with associated source titles, domains, and URLs.
- **`DERIVED`**: Computed by deterministic code (e.g., Haversine distance, constraint matrices, rank scores).

---

## 8. Deterministic Ranking Logic & Position Lifecycle

**LLMs do not choose the winner.** Candidate ranking is computed by deterministic Python logic using explicit scoring rules:

### Position Lifecycle
1. **Places Retrieval Position ($P_{\text{retrieval}}$):** The initial 1-indexed rank returned by Google Places Text Search.
2. **Evidence-Enriched Position ($P_{\text{evidence}}$):** Position after incorporating multi-source evidence and initial constraint satisfaction.
3. **Final Recommendation Position ($P_{\text{rec}}$):** Final rank after applying the full additive scoring formula.
4. **Rank Movement ($\Delta$):**
   $$\Delta = P_{\text{retrieval}} - P_{\text{rec}}$$
   - $\Delta > 0$: Candidate moved up (`▲ +N`) due to strong constraint satisfaction or proximity.
   - $\Delta < 0$: Candidate moved down (`▼ -N`) due to failed hard constraints or distant location.
   - $\Delta = 0$: Candidate position unchanged (`● Unchanged`).

### Transparent Score Breakdown
Candidate scores are decomposed into distinct, inspectable components:

$$\text{Total Score} = \text{Hard Points} + \text{Preference Points} + \text{Proximity Points} + \text{Quality Points} + \text{Penalties}$$

- **Hard Constraints:** `+25.0` per supported constraint; `-35.0` penalty per unsatisfied constraint.
- **Preferences:** `+10.0` per supported preference; `-10.0` deduction per unsatisfied preference.
- **Unknown Constraints:** Neutral weight (`0.0`), preventing missing web claims from penalizing valid local businesses.
- **Proximity Bonus:** Smoothly decaying Haversine distance bonus up to `+12.0` points:
  $$\text{Bonus} = \frac{12.0}{1.0 + \text{Distance in Miles}}$$
- **Quality Signal:** Bounded secondary bonus based on Google rating (up to `+6.0` pts) and logarithmically saturated user review count (up to `+4.0` pts).
- **Category Eligibility:** Hard filter ensuring candidate place types align with the user's requested category.

---

## 9. Technology Stack

| Technology | Role in Architecture |
| :--- | :--- |
| **Gemini API (`gemini-3.6-flash` / `gemini-3.5-flash-lite`)** | Natural language intent extraction, query fan-out planning, and grounded answer synthesis with resilient fallback. |
| **Google GenAI Python SDK (`google-genai`)** | Official Python interface for structured output schemas and search grounding. |
| **Google ADK (`google-adk`)** | Agentic orchestration framework structuring reasoning, tools, and execution steps. |
| **Google Search Grounding** | Web search tool grounding LLM reasoning with real-time web citations and sources. |
| **Google Places API (New)** | Structured local search, entity details, operating hours, and reference location resolution. |
| **Google Maps Static API** | Rendered map imagery displaying labeled markers (`A`, `B`, `C`) for top-ranked venues. |
| **Streamlit** | Interactive Journey Inspector UI for step-by-step pipeline inspection across four capability tabs. |
| **Pydantic / Pydantic Settings** | Strict schema validation, data modeling, and environment configuration. |
| **Docker** | Multi-stage, non-root container packaging (`python:3.12-slim`). |
| **Google Artifact Registry** | Secure container image repository in GCP. |
| **Google Cloud Run** | Fully managed serverless container runtime. |
| **Google Secret Manager** | Secure, decoupled runtime storage for Gemini and Google Maps API keys. |
| **pytest / Ruff / mypy** | Unit testing (340+ tests), linting, and strict static type checking. |

---

## 10. Project Structure

```text
ai-search-journey-lab/
├── assets/                          # UI assets and branding logos
│   ├── ai-search-journey-lab.png    # Live Journey Inspector screenshot
│   ├── gdg.svg
│   ├── gdg.jpeg
│   └── google-for-startup.webp
├── scripts/                         # Automation and demo CLI scripts
│   ├── bootstrap_gcp.sh             # One-time GCP infrastructure provisioning
│   ├── bootstrap_bigquery_v3.sh     # BigQuery dataset & table setup for V3/V4
│   ├── deploy_cloud_run.sh          # Automated Docker build, push, and Cloud Run deploy
│   ├── delete_cloud_run.sh          # Safe cleanup script for Cloud Run service & images
│   ├── run_app.py                   # Local Streamlit runner
│   ├── demo_journey_v2.py           # v2.0.0 Search Journey Optimization (SJO) CLI demo
│   ├── demo_intent_extraction.py    # Intent parsing CLI demo
│   ├── demo_fanout.py               # Query fan-out CLI demo
│   ├── demo_places.py               # Places retrieval CLI demo
│   ├── demo_search_grounding.py     # Search grounding CLI demo
│   ├── demo_evidence.py             # Evidence aggregation CLI demo
│   ├── demo_constraints.py          # Constraint matrix CLI demo
│   ├── demo_ranking.py              # Deterministic ranking CLI demo
│   ├── demo_static_map.py           # Maps preview CLI demo
│   ├── demo_answer.py               # Grounded answer synthesis CLI demo
│   ├── demo_visibility_v3.py        # V3 AI Visibility scan CLI demo
│   ├── demo_visibility_agent_v4.py  # V4 AI Visibility Agent CLI demo
│   └── demo_adk.py                  # End-to-end ADK agent CLI demo
├── src/ai_search_journey/           # Core library package
│   ├── __init__.py                  # Package exports
│   ├── models.py                    # Domain Pydantic schemas and Enums
│   ├── config.py                    # Environment and settings configuration
│   ├── planner.py                   # Structured intent extraction
│   ├── fanout.py                    # Query fan-out generation
│   ├── places.py                    # Google Places API client
│   ├── search.py                    # Google Search grounding client
│   ├── normalize.py                 # Candidate deduplication and normalization
│   ├── evidence.py                  # Multi-source evidence aggregation
│   ├── constraints.py               # Deterministic constraint evaluation engine
│   ├── ranking.py                   # Scoring and explainable ranking engine
│   ├── static_map.py                # Google Maps Static API URL generator
│   ├── answer.py                    # Grounded answer synthesis with resilience
│   ├── app.py                       # Streamlit Journey Inspector application (4 tabs)
│   ├── ui_assets.py                 # UI branding and logo helpers
│   ├── ui_formatters.py             # UI table, badge, and timeline formatters
│   ├── adk/                         # Google ADK agent implementation
│   │   ├── __init__.py
│   │   ├── agent.py                 # SearchJourneyAgent root orchestrator
│   │   └── tools.py                 # ADK tool wrappers
│   └── visibility/                  # V3/V4 AI Visibility engine & Agent
│       ├── models.py                # Visibility schemas & brand metrics
│       ├── extractor.py             # Signal extractor & Gemini grounding
│       ├── metrics.py               # Share of Voice & visibility calculator
│       ├── repository.py            # BigQuery persistence & schema manager
│       ├── mcp_server.py            # Read-only MCP analytical tools
│       ├── agent.py                 # V4 ADK conversational agent
│       ├── ui.py                    # V3 AI Visibility Streamlit tab
│       └── ui_v4.py                 # V4 AI Visibility Agent Streamlit tab
├── tests/                           # Comprehensive test suite (340+ tests)
├── Dockerfile                       # Production multi-stage Dockerfile
├── .dockerignore                    # Build context exclusions
├── pyproject.toml                   # Project dependencies and tool configurations
└── README.md                        # Documentation
```

---

## 11. Local Setup & Testing

### Prerequisites
- Python 3.12+
- Google Cloud Project with Gemini API and Places API enabled
- Valid API keys for Gemini and Google Maps

### Installation

```bash
# 1. Clone repository
git clone https://github.com/hastimal.jangid/ai-search-journey-lab.git
cd ai-search-journey-lab

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install package and development dependencies
pip install -e ".[bigquery,v4-agent,dev]"

# 4. Configure environment variables
cp .env.example .env
```

Edit `.env`:
```env
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
GEMINI_MODEL="gemini-3.6-flash"
GEMINI_FALLBACK_MODEL="gemini-3.5-flash-lite"
GOOGLE_MAPS_API_KEY="YOUR_GOOGLE_MAPS_API_KEY"
LOG_LEVEL="INFO"
```

### Running Tests & Quality Checks

```bash
# Run test suite
python -m pytest -v

# Run linter
python -m ruff check .

# Run static type checker
python -m mypy src
```

---

## 12. Running the Journey Inspector Locally

Launch the Streamlit GUI:

```bash
streamlit run src/ai_search_journey/app.py
```

Access the UI at `http://localhost:8501`.

### Application Architecture: Four Capability Tabs

The Journey Inspector organizes inspection and evaluation into four dedicated capability tabs:

```text
┌───────────────────────────┬───────────────────────────┬───────────────────────────┬───────────────────────────┐
│  Search to Decision [V1]  │   Journey Analysis [V2]   │    AI Visibility [V3]     │ AI Visibility Agent [V4]  │
├───────────────────────────┼───────────────────────────┼───────────────────────────┼───────────────────────────┤
│ • Interactive AI search   │ • Multi-query candidate   │ • Brand presence & SOV    │ • Conversational natural  │
│ • Grounded recommendations│   retrieval provenance    │ • Narrative mention rate  │   language agent          │
│ • Constraint matrix       │ • Explainable rank        │ • Owned citation analysis │ • Grounded in read-only   │
│ • Static map preview      │   movement (Δ) tracking   │ • Competitor benchmark    │   BigQuery scan history   │
│ • ADK execution trace     │ • Transparent score       │ • BigQuery or in-memory   │ • ADK + local MCP tools   │
│                           │   decomposition           │   session history         │ • Discovery-first answers │
└───────────────────────────┴───────────────────────────┴───────────────────────────┴───────────────────────────┘
```

- **Search to Decision [V1]:** End-to-end user-facing search journey from question to grounded recommendations, constraint validation, static map rendering, and live developer execution traces.
- **Journey Analysis [V2]:** Deep-dive provenance tracking, transparent score breakdowns (hard points, preferences, proximity, penalties), and deterministic rank movement explanations ($\Delta$).
- **AI Visibility [V3]:** Reuses completed search journeys to quantify brand presence, narrative mention rates, recommendation rates, owned citation rates, and share of voice against competitors.
- **AI Visibility Agent [V4]:** Natural language agent grounded in persisted BigQuery visibility scans, answering strategic questions via read-only Model Context Protocol (MCP) analytics tools.

---

### AI Visibility Agent [V4] (Read-Only Conversational Agent)

The **V4 AI Visibility Agent** provides a natural language conversational interface over persisted V3 BigQuery visibility history.

> [!IMPORTANT]
> **Strict Read-Only Architecture:**
> - V4 is an **AI Visibility Agent**, not a new scan engine. It strictly queries historical data already persisted by V3 scans in BigQuery.
> - **No write operations:** V4 never writes to BigQuery, inserts records, or triggers new V1/V3 live scans.
> - **Isolated execution:** Uses parameterized BigQuery queries without dynamic SQL generation.

#### Architecture Flow

```mermaid
flowchart TD
    User([Streamlit UI Composer]) -->|Natural language question| Agent[Gemini / Google ADK Agent]
    Agent -->|Stdio JSON-RPC tool calls| MCP[Local MCP Server]
    MCP -->|Parameterized SQL| BQ[(BigQuery V3 History)]
    BQ -.->|Historical metrics & scan bounds| MCP
    MCP -.->|Structured tool results| Agent
    Agent -->|Grounded conversational answer| User

    subgraph Boundaries ["Strict Operational Boundaries"]
        style Boundaries fill:#1e293b,stroke:#dc2626,stroke-width:1px,stroke-dasharray: 5 5
        B1["🔒 Read-Only Analytics (No writes to BigQuery)"]
        B2["🚫 Isolated from V1/V3 (Cannot trigger live scans)"]
    end
```

#### Grounding & Discovery Behavior
- **Discovery-First Grounding:** Before analyzing broad questions (e.g. asking about "available history", "latest trends", or when a brand/date range is omitted), the agent calls `get_available_history` to discover actual scan counts, earliest/latest scan timestamps, and real persisted `brand_id` values. It never invents placeholder brands (e.g. default "nike") or arbitrary date ranges.
- **Brand Scope:** Broad history prompts compare across available discovered brands; brand-specific queries should reference real persisted `brand_id` identifiers.
- **Trend Inferences:** Trend analysis strictly requires multiple distinct scan dates. Multiple scans executed on a single day provide window comparisons but do not imply a chronological trend.

#### Try V4: Example Prompts
You can query the V4 agent using natural questions such as:
- `Give me a visibility summary for the available history. Use the most recent available scan window.`
- `What should I do for better ranking compared to my competitors?`
- `Analyze citations for pullman_coffee using the most recent available scan window.`

*(Note: Brand IDs like `pullman_coffee` must exist in your persisted BigQuery visibility history to return brand-specific metrics).*

---

## 13. Running with Docker

### Build Image
```bash
docker build -t ai-search-journey-lab:local .
```

### Run Container
```bash
docker run --rm \
  -p 8080:8080 \
  --env-file .env \
  ai-search-journey-lab:local
```

Access the application at `http://localhost:8080`.

Verify container health:
```bash
curl http://localhost:8080/_stcore/health
```

---

## 14. Google Cloud Deployment

The repository provides repeatable automation scripts for deployment to **Google Cloud Run**.

### 1. One-Time Infrastructure Bootstrap
Enables GCP APIs, creates an Artifact Registry repository, provisions a dedicated runtime service account (`ai-search-journey-runner`), and sets up Secret Manager placeholders:

```bash
./scripts/bootstrap_gcp.sh
```

Add your production API keys to Secret Manager:
```bash
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=- --project=ai-search-journey-lab
echo -n "YOUR_GOOGLE_MAPS_API_KEY" | gcloud secrets versions add google-maps-api-key --data-file=- --project=ai-search-journey-lab
```

### 2. Deploy or Update
Builds the `linux/amd64` container image using Docker Buildx, pushes to Artifact Registry, deploys to Cloud Run with Secret Manager mounting, and runs a health check:

```bash
./scripts/deploy_cloud_run.sh
```

### 3. BigQuery Bootstrap (V3 AI Visibility)
To initialize or preview BigQuery schema tables and control locks for persistent AI Visibility tracking (auto-derives project from active `gcloud` config, with optional `--project` override):

```bash
# Dry run (previews planned actions and DDL without executing changes):
./scripts/bootstrap_bigquery_v3.sh

# Or with explicit project / dataset overrides:
./scripts/bootstrap_bigquery_v3.sh --project YOUR_PROJECT_ID --dataset ai_search_journey_v3 --location US

# Apply schema setup and verify tables:
./scripts/bootstrap_bigquery_v3.sh --apply
```

### 4. Safe Cleanup
Removes the Cloud Run service and Artifact Registry container images while preserving secrets, the repository, and the service account:

```bash
# Interactive confirmation:
./scripts/delete_cloud_run.sh

# Non-interactive:
./scripts/delete_cloud_run.sh --yes
```

---

## 15. Design Principles

1. **Transparent over Magical:** Every intermediate artifact—intent, fan-outs, executed queries, raw evidence, and constraint evaluations—is preserved and inspectable.
2. **Evidence before Explanation:** Rationales cite specific structured fields or web sources before generating prose.
3. **Deterministic Decisions:** Scoring, constraint matching, distance, and ranking are strictly deterministic. LLMs do not pick the winner.
4. **Unknown is Not Failure:** Absence of web confirmation for qualitative attributes does not disqualify legitimate local businesses.
5. **Preserve Provenance:** All evidence maintains its exact source identifier and retrieval task origin.
6. **Separate Planning from Retrieval:** Planning query generation is decoupled from API tool execution.
7. **Agents Only Where Reasoning is Needed:** LLMs are applied for semantic parsing, dynamic fan-out planning, and synthesis—not for table joins, filtering, or scoring.

---

## 16. Current Scope & Limitations

- **Educational & Architectural Reference:** Designed to explain AI search mechanics; does not replicate Google Search internal infrastructure or Google AI Mode.
- **Dynamic Retrieval Variance:** Live Places and web search results reflect real-time web state and may vary across queries.
- **Qualitative Signal Sparsity:** Attributes such as "quiet atmosphere" or "large group tables" may remain `UNKNOWN` when web sources lack explicit commentary.
- **Operating Hours Context:** Opening hours evaluation checks regular weekly schedule data; explicit holiday/date schedules require dedicated date context.
- **Canonical Universe:** The current implementation uses Google Places candidates as the canonical venue universe, with Google Search providing supporting qualitative evidence.

---

## 17. Future Research & Extensions

- **Benchmark & Evaluation Suite:** Systematic accuracy and latency benchmarking against diverse query sets.
- **Parallel Retrieval Optimization:** Asynchronous execution of fan-out tool calls to minimize total journey latency.
- **Expanded Location Tasks:** Support for route-based and multi-stop discovery journeys.
- **Search Journey Optimization (SJO):** Empirical analysis of how structured entity data influences AI search retrieval and citation visibility.

---

## 18. Contributing

Contributions, feedback, and experiment ideas are welcome!

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/new-search-capability`.
3. Ensure all tests and linters pass:
   ```bash
   python -m pytest -v && python -m ruff check . && python -m mypy src
   ```
4. Submit a Pull Request.

---

## 19. Author

**Hastimal Jangid**  
*Cloud, Data & AI Architect | Researcher | IEEE Senior Member*

- **Website:** [hastimal.github.io](https://hastimal.github.io)
- **GitHub:** [@hastimal](https://github.com/hastimal)
- **LinkedIn:** [Hastimal Jangid](https://www.linkedin.com/in/hastimaljangid/)

## 20. Contributors

Contributions are welcome. Contributors are recognized through merged pull requests and the repository’s GitHub contributor graph.

- [Harsh Jangid](https://github.com/harshjangid1015) — OpenTelemetry and observability (V5)

See the full contributor history on [GitHub](https://github.com/hastimal/ai-search-journey-lab/graphs/contributors).
---

## 21. Appendix: Full Journey Analysis Trace

<details>
<summary><strong>🔍 Click to expand full-page Journey Analysis [V2] deep-dive trace</strong></summary>
<br>

![Journey Analysis Full Deep-Dive](assets/screenshots/v2-journey-analysis-full.png)

</details>

---

## 22. License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
