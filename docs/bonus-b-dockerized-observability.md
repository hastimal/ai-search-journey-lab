# Bonus-B: Dockerized Grafana & OpenTelemetry Observability

This guide details the local, Docker Compose-based observability stack for **AI Search Journey Lab**, extending the process-local V5 OpenTelemetry instrumentation to a complete local observability architecture with **Grafana**, **Prometheus**, and **Grafana Tempo**.

---

## 1. Architecture Overview

```text
AI Search Journey Lab (Python / Streamlit)
  │
  ├─ In-Memory Trace Store (V5 UI tab in Streamlit - always active)
  │
  └─ OpenTelemetry Trace & Metric Exporters (Optional, enabled via OTEL_EXPORTER_OTLP_ENDPOINT)
       │
       ▼ (OTLP HTTP JSON /v1/traces and /v1/metrics on port 4318)
  OpenTelemetry Collector (otel-collector:4317 / 4318)
       ├─ Traces ───► Grafana Tempo (tempo:4317 / 3200)
       │              └─ Distributed trace storage & TraceQL search
       │
       └─ Metrics ──► Prometheus (prometheus:9090 scrapes otel-collector:8889)
                      └─ Time-series metric storage & queries
                           │
                           ▼
                     Grafana Dashboard (localhost:3000)
                      ├─ AI Search Journey Overview Dashboard
                      ├─ Workflow execution counts & durations (V1, V3, V4)
                      ├─ V4 AgentOps TraceQL table
                      └─ Seamless trace-to-metric correlation
```

---

## 2. Privacy & Telemetry Guard

Redaction is strictly enforced at every layer before telemetry leaves the Python process:

1. **No Sensitive Content in Traces or Metrics**:
   - Prompts, raw queries, user input text, and model responses are never exported.
   - API keys, OAuth tokens, and passwords matching known formats are redacted.
   - Database queries (e.g. BigQuery SQL) are not exported.
   - URLs with query parameters have query strings removed.
2. **Safe Labels and Attributes**:
   - Metrics label dimensions only contain safe, low-cardinality identifiers: `stage` (`v1`, `v3`, `v4`, `custom`), and `status` (`ok`, `error`).
   - Trace IDs, session IDs, and user text are strictly excluded from metric labels.
   - OpenTelemetry span attributes only contain structural metadata (e.g. `workflow.stage`, `agent.operation`, `duration_ms`).
3. **Local-Only Export**:
   - Telemetry is buffered in-process and can be exported to the local OpenTelemetry collector over `http://localhost:4318`. No data is ever sent to external third-party or SaaS telemetry vendors.

---

## 3. V4 AgentOps Trace Hierarchy

V4 Visibility Agent chat interactions emit a structured span hierarchy where LLM generation and MCP tool execution latencies are cleanly measured:

```text
v4.agent.chat_turn
├── v4.agent.load_context      (Context preparation & session loading)
├── v4.agent.gemini_generate   (Model reasoning, token generation & MCP tool execution)
└── v4.agent.response          (Response formatting & presentation)
```

---

## 4. Local Developer Workflow

### Recommended: One-Step Launch

Launch the entire local observability stack, verify provisioning, and start Streamlit in one command:

```bash
python scripts/run_app_locally.py
```

This helper script automatically:
1. Starts the Docker Compose observability stack (`otel-collector`, `tempo`, `prometheus`, `grafana`).
2. Polls health endpoints until all services are ready.
3. Confirms dashboard and datasource provisioning in Grafana.
4. Starts the Streamlit application.

---

### Alternative: Manual Step-by-Step Launch

<details>
<summary><strong>Click to view manual Docker Compose instructions</strong></summary>

#### Step 1: Start the Observability Stack

Launch the Docker Compose stack in the background:

```bash
docker compose -f docker-compose.observability.yml up -d
```

Verify that all services are healthy:

```bash
docker compose -f docker-compose.observability.yml ps
```

#### Step 2: Configure Application Environment

Set the OTLP exporter endpoint in your `.env` or shell (disabled by default):

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
export OTEL_SERVICE_NAME="ai_search_journey"
export OTEL_METRICS_ENABLED="true"
export GRAFANA_URL="http://localhost:3000"
```

#### Step 3: Run AI Search Journey Lab

Start the Streamlit application:

```bash
streamlit run src/ai_search_journey/app.py
```

#### Step 4: Stop the Stack

To cleanly tear down the observability containers and remove temporary volumes:

```bash
docker compose -f docker-compose.observability.yml down -v
```

</details>

---

## 5. Service Endpoints & Access

| Service | Local URL | Default Credentials | Description |
| :--- | :--- | :--- | :--- |
| **Streamlit App** | [http://localhost:8502](http://localhost:8502) (or `8501`) | None | Journey Inspector & Observability [V5] UI |
| **Grafana** | [http://localhost:3000](http://localhost:3000) | `admin` / `admin` (Anonymous login enabled) | Visual dashboards, trace explorer, metric charts |
| **Grafana AgentOps Dashboard** | [http://localhost:3000/d/ai-search-journey-overview/ai-search-journey-observability-overview](http://localhost:3000/d/ai-search-journey-overview/ai-search-journey-observability-overview) | Anonymous / Viewer | Overview dashboard with V4 TraceQL integration |
| **Tempo Explore** | [http://localhost:3000/explore](http://localhost:3000/explore) | Anonymous / Viewer | Distributed trace exploration |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | None | Prometheus query explorer and target health |
| **Grafana Tempo** | [http://localhost:3200](http://localhost:3200) | None | Distributed trace backend & search |
| **OTel Collector** | `http://localhost:4318` (HTTP)<br>`http://localhost:4317` (gRPC) | None | Telemetry ingestion endpoint |

---

## 6. Provisioned Grafana Assets

The Docker stack automatically provisions:
1. **Datasources**:
   - **Prometheus** (`http://prometheus:9090`): Configured as default metrics datasource.
   - **Tempo** (`http://tempo:3200`): Configured with trace search and trace-to-metrics queries.
2. **Dashboard**:
   - **AI Search Journey — Observability Overview**: Displays observed journey execution increments, V3 visibility scans, V4 agent chat turns, stage latencies, error counts, and a dedicated V4 AgentOps TraceQL table.

---

## 7. Resilience & Graceful Degradation

- **Optional by Design**: If Docker is not running or `OTEL_EXPORTER_OTLP_ENDPOINT` is omitted, the app operates 100% in-memory with zero network overhead.
- **Fail-Safe**: If the collector or Tempo container becomes unreachable during execution, telemetry exports fail silently in background worker threads without degrading or crashing user searches or agent workflows.
- **No Cloud Run Impact**: This observability stack is strictly local development and demo infrastructure and does not modify Cloud Run deployment targets.

---

## 8. Troubleshooting

- **Grafana Shows "No Data"**:
  - Ensure `OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"` is set before starting Streamlit.
  - Run a workflow in the app (e.g., V1 Search or V4 Chat) to generate traces.
  - Check Prometheus targets at [http://localhost:9090/targets](http://localhost:9090/targets) to ensure `otel-collector` is UP.
- **Port Conflict**:
  - If port `3000`, `9090`, or `4318` is already in use by another local service, adjust port mappings in `docker-compose.observability.yml`.

