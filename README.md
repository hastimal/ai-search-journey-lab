# AI Search Journey Lab

> A transparent reference implementation for understanding how an AI-powered search journey can move from user intent → query fan-out → retrieval → grounding → evidence → deterministic constraint evaluation → ranking → grounded recommendations.

---

> **Important Architectural Scope:**  
> This project uses public Google developer technologies (Gemini API via Google GenAI SDK, Google Places API (New), Google Search Grounding, Google Maps Static API, and Google Cloud Run) to demonstrate foundational AI search concepts including structured intent decomposition, query fan-out, multi-source retrieval, web grounding, deterministic constraint evaluation, explainable ranking, and grounded synthesis.
>
> *AI Mode* and *AI Overviews* are proprietary Google Search product experiences and are **not** APIs used by this project.

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
- **Google Places API (New)** retrieves structured local entity data (names, coordinates, operating hours, ratings, types, Google Maps URLs).
- **Google Search Grounding** gathers real-time, qualitative web evidence, source domains, and citations.
- **Deterministic Python** normalizes candidates, evaluates hard constraints and preferences, computes proximity, and calculates explainable ranking scores.
- **Gemini** explains and synthesizes grounded recommendations strictly for the deterministically ranked Top 3 candidates.

---

## 2. Demo

The Journey Inspector makes the complete AI search journey visible instead of showing only a final recommendation.

It exposes:
- parsed search intent
- dynamic planner query fan-out
- Google Places retrieval
- executed Google Search grounding queries
- evidence provenance
- deterministic constraint evaluation
- ranking and proximity
- Top 3 recommendations
- Google Maps Static API preview
- grounded final answer
- ADK developer trace
- per-step execution timing

![AI Search Journey Lab Demo](assets/ai-search-journey-lab.png)

> **Example:** Finding a coffee shop near Geekdom San Antonio for six people to work together, preferably quiet, and open after 8 PM. The UI keeps unsupported or unavailable evidence explicitly marked as unverified (`?` unknown) rather than converting unknowns into false claims.
>
> **Execution Summary:** `✅ Search Journey Complete · 53.0s`
>
> In this example, the complete journey finished in approximately 53 seconds. The execution panel is collapsible, making it easy to switch between the final recommendations (high-level result view) and the underlying intent extraction, fan-out, retrieval, grounding, evidence aggregation, constraint evaluation, and ranking steps (detailed execution trace). Runtime varies between executions because external retrieval and Google Search grounding calls are live.

### Example Query

```text
Find a coffee shop near Geekdom San Antonio for 6 people to work together, preferably quiet, and open after 8 PM.
```

---

## 3. Capabilities Demonstrated

- **Structured Intent Extraction:** Multi-label classification (`informational`, `navigational`, `commercial`, `transactional`, `local_discovery`) with structured extraction of reference locations, categories, operating hours, group sizes, hard constraints, and preferences.
- **Dynamic Query Fan-Out:** LLM-driven query planner decomposing complex requests into targeted retrieval tasks routed to appropriate tools.
- **Multi-Source Retrieval:**
  - **Google Places API (New):** Structured candidate discovery, place details, and reference location resolution.
  - **Gemini + Google Search Grounding:** Dynamic grounding queries, web snippets, citations, and capture of actual executed Google Search queries.
- **Candidate Normalization & Deduplication:** Stable entity consolidation using unique Google Place IDs with cross-query attribute merging.
- **Evidence Aggregation & Provenance:** Unifies structured Places signals and web claims while preserving source tags (`GOOGLE PLACES`, `GOOGLE SEARCH`, `DERIVED`) and fan-out task IDs (`F1`, `F2`, `F3`, etc.).
- **Deterministic Constraint Matrix:** 3-state evaluation semantics (`SUPPORTED`, `UNKNOWN`, `NOT_SATISFIED`), enforcing that `UNKNOWN != false`.
- **Explainable Scoring & Proximity:** Weighted scoring with bounded proximity bonuses (Haversine formula), review saturation curves, and strict category eligibility validation.
- **Visual Mapping:** Dynamic Google Maps Static API preview with ranked markers (`A`, `B`, `C`) and direct Google Maps destination links.
- **Grounded Answer Generation:** Structured synthesis with per-candidate summaries, evidence citations, match rationales, and explicit unknowns.
- **Google ADK Orchestration:** Agent-driven workflow orchestration separating reasoning from deterministic evaluation.
- **Streamlit Journey Inspector:** Transparent UI visualizing execution steps, wall-clock timing, fan-out tasks, executed search queries, evidence claims, constraint matrices, and developer traces.
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
                         Structured Intent
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
                                ▼
                              Top 3
                    ┌───────────┴───────────┐
                    ▼                       ▼
            Google Maps URLs         Maps Static API
                                     (A / B / C Markers)
                    └───────────┬───────────┘
                                │
                                ▼
                             Gemini
                     (Grounded Explanation)
                                │
                                ▼
                   Streamlit Journey Inspector
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

| Status | Meaning | Scoring Impact |
| :--- | :--- | :--- |
| **`SUPPORTED`** | Positive evidence confirms the constraint is satisfied. | Positive bonus applied (+25 hard, +10 pref). |
| **`UNKNOWN`** | Neither Places nor Search contained evidence confirming or denying the constraint. | **Neutral (0 pts). `UNKNOWN != false`.** |
| **`NOT_SATISFIED`** | Retrieved evidence directly contradicts the constraint. | Strong penalty (-35 hard, -10 pref). |

### Sample Constraint Matrix

| Candidate | Open After 8 PM | Group Capacity (6) | Quiet Atmosphere | Work Friendly |
| :--- | :---: | :---: | :---: | :---: |
| **Kafe Krave** | `✓ PLACES [F2]` | `✓ SEARCH [F3]` | `?` | `✓ SEARCH [F4]` |
| **Local Candidate B** | `✗ PLACES [F1]` | `?` | `?` | `?` |

### Provenance Tracking
Every evidence item maintains strict source provenance:
- **`GOOGLE PLACES`**: Derived directly from verified Google Places API attributes (e.g. `currentOpeningHours`).
- **`GOOGLE SEARCH`**: Extracted from web search grounding chunks with associated source titles, domains, and URLs.
- **`DERIVED`**: Computed by deterministic code (e.g., Haversine distance, constraint matrices, rank scores).

---

## 8. Deterministic Ranking Logic

**LLMs do not choose the winner.** Candidate ranking is computed by deterministic Python logic using explicit scoring rules:

- **Hard Constraints:** Strong positive weight (`+25.0`) when satisfied; severe penalty (`-35.0`) when failed.
- **Preferences:** Modest bonus (`+10.0`) when satisfied; minor deduction (`-10.0`) when failed.
- **Unknown Constraints:** Neutral weight (`0.0`), preventing missing web claims from penalizing valid local businesses.
- **Proximity Bonus:** Smoothly decaying Haversine distance bonus up to `+12.0` points:
  $$\text{Bonus} = \frac{12.0}{1.0 + \text{Distance in Miles}}$$
- **Quality Signal:** Bounded secondary bonus based on Google rating (up to `+6.0` pts) and logarithmically saturated user review count (up to `+4.0` pts).
- **Category Eligibility:** Hard filter ensuring candidate place types align with the user's requested category.

---

## 9. Technology Stack

| Technology | Role in Architecture |
| :--- | :--- |
| **Gemini API (`gemini-2.5-flash`)** | Natural language intent extraction, query fan-out planning, and grounded answer synthesis. |
| **Google GenAI Python SDK (`google-genai`)** | Official Python interface for structured output schemas and search grounding. |
| **Google ADK (`google-adk`)** | Agentic orchestration framework structuring reasoning, tools, and execution steps. |
| **Google Search Grounding** | Web search tool grounding LLM reasoning with real-time web citations and sources. |
| **Google Places API (New)** | Structured local search, entity details, operating hours, and reference location resolution. |
| **Google Maps Static API** | Rendered map imagery displaying labeled markers (`A`, `B`, `C`) for top-ranked venues. |
| **Streamlit** | Interactive Journey Inspector UI for step-by-step pipeline inspection. |
| **Pydantic / Pydantic Settings** | Strict schema validation, data modeling, and environment configuration. |
| **Docker** | Multi-stage, non-root container packaging (`python:3.12-slim`). |
| **Google Artifact Registry** | Secure container image repository in GCP. |
| **Google Cloud Run** | Fully managed serverless container runtime. |
| **Google Secret Manager** | Secure, decoupled runtime storage for Gemini and Google Maps API keys. |
| **pytest / Ruff / mypy** | Unit testing (140+ tests), linting, and strict static type checking. |

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
│   ├── deploy_cloud_run.sh          # Automated Docker build, push, and Cloud Run deploy
│   ├── delete_cloud_run.sh          # Safe cleanup script for Cloud Run service & images
│   ├── run_app.py                   # Local Streamlit runner
│   ├── demo_intent_extraction.py    # Intent parsing CLI demo
│   ├── demo_fanout.py               # Query fan-out CLI demo
│   ├── demo_places.py               # Places retrieval CLI demo
│   ├── demo_search_grounding.py     # Search grounding CLI demo
│   ├── demo_evidence.py             # Evidence aggregation CLI demo
│   ├── demo_constraints.py          # Constraint matrix CLI demo
│   ├── demo_ranking.py              # Deterministic ranking CLI demo
│   ├── demo_static_map.py           # Maps preview CLI demo
│   ├── demo_answer.py               # Grounded answer synthesis CLI demo
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
│   ├── answer.py                    # Grounded answer synthesis
│   ├── app.py                       # Streamlit Journey Inspector application
│   ├── ui_assets.py                 # UI branding and logo helpers
│   ├── ui_formatters.py             # UI table, badge, and timeline formatters
│   └── adk/                         # Google ADK agent implementation
│       ├── __init__.py
│       ├── agent.py                 # SearchJourneyAgent root orchestrator
│       └── tools.py                 # ADK tool wrappers
├── tests/                           # Comprehensive test suite (140+ tests)
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
git clone https://github.com/hastimal/ai-search-journey-lab.git
cd ai-search-journey-lab

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install package and development dependencies
pip install -e ".[dev]"

# 4. Configure environment variables
cp .env.example .env
```

Edit `.env`:
```env
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
GEMINI_MODEL="gemini-2.5-flash"
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

### 3. Safe Cleanup
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

---

## 20. License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
