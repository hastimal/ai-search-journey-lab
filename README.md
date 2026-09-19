# AI Search Journey Lab

Research and engineering experiments exploring how modern AI systems discover, retrieve, rank, ground, and recommend information.

This project explores:

- AI Search
- Query fan-out
- Retrieval
- Ranking
- Grounding
- Citations
- Recommendation
- Search journey optimization
- Location-aware discovery
- Google Search
- Google Maps
- LLM discovery
- AI answer systems

## Goal

The goal is to understand how search is evolving from:

```text
Query
  |
  v
Ranked Links
```

into:

```text
User Intent
   |
   v
Query Fan-Out
   |
   v
Multiple Retrieval Sources
   |
   v
Evidence Ranking
   |
   v
Reasoning
   |
   v
Recommendation / Answer
```

## Research Questions

- How do AI systems expand a single query into multiple searches?
- How should retrieved evidence be ranked?
- What makes a source authoritative?
- How do location and context affect recommendations?
- How should AI systems preserve citations and provenance?
- How do AI answers differ from traditional search rankings?
- How can businesses and information providers become easier for AI systems to discover and understand?

## Planned Labs

- Query fan-out
- Search intent decomposition
- Evidence retrieval
- Evidence ranking
- Citation preservation
- Location-aware discovery
- Search + Maps workflows
- Multi-agent search
- Search evaluation

## Deployment (Google Cloud Run)

### 1. One-Time Setup
Run the bootstrap script to enable APIs, create the Artifact Registry repository, configure the runtime service account, and provision Secret Manager secret holders:

```bash
./scripts/bootstrap_gcp.sh
```

If secret versions have not been added yet, add your API keys securely:

```bash
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=- --project=ai-search-journey-lab
echo -n "YOUR_GOOGLE_MAPS_API_KEY" | gcloud secrets versions add google-maps-api-key --data-file=- --project=ai-search-journey-lab
```

### 2. Deploy or Update
Build the multi-arch `linux/amd64` container image, push to Artifact Registry, and deploy directly to Cloud Run:

```bash
./scripts/deploy_cloud_run.sh
```

## Roadmap

- v0.1 - Query Fan-Out
- v0.2 - Multi-Source Retrieval
- v0.3 - Evidence Ranking
- v0.4 - Grounding & Citations
- v0.5 - Location-Aware Search
- v0.6 - Multi-Agent Search
- v0.7 - Search Evaluation

## Author

**Hastimal Jangid**

Cloud, Data & AI Architect | Researcher | IEEE Senior Member

Research interests include AI Search, LLM retrieval, grounding, ranking, recommendation, Agentic AI, and trustworthy AI systems.

Website: https://hastimal.github.io  
GitHub: https://github.com/hastimal
