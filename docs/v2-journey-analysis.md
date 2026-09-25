# Search Journey Optimization (SJO) [V2]: Positional Movement & Provenance

> **Milestone 3 Architectural Article**<br>
> Understanding how a local entity moves from its initial **Places retrieval position** through multi-source evidence enrichment to its **final recommendation rank** with transparent score breakdowns and explainable rank movement ($\Delta$).

---

## 1. Overview: The Search Journey Lifecycle

Traditional SEO optimizes for initial keyword retrieval position. In an AI-assisted search journey, initial retrieval is only the first step. Candidate venues undergo dynamic evidence aggregation and constraint evaluation before reaching the final recommendation stage.

```text
Places Retrieval Position (P_retrieval)
                   │
                   ▼
Evidence-Enriched Position (P_evidence)
                   │
                   ▼
Final Recommendation Position (P_rec)
                   │
                   ▼
Rank Movement: Δ = P_retrieval - P_rec (▲ Up, ▼ Down, ● Unchanged)
```

### Positional Metrics & Score Decomposition

- **Places Retrieval Position ($P_{\text{retrieval}}$)**: The initial 1-indexed rank returned by Google Places Text Search.
- **Evidence-Enriched Position ($P_{\text{evidence}}$)**: Position after incorporating multi-source search grounding evidence.
- **Final Recommendation Position ($P_{\text{rec}}$)**: Final deterministic rank after applying the full additive scoring formula.
- **Rank Movement ($\Delta$)**: Quantified movement ($\Delta = P_{\text{retrieval}} - P_{\text{rec}}$) with deterministic movement explanations.
- **Transparent Score Decomposition**:
  $$\text{Total Score} = \text{Hard Points} + \text{Preference Points} + \text{Proximity Points} + \text{Quality Points} + \text{Penalties}$$

---

## 2. Run and Inspect It Yourself

You can run the full Search Journey Optimization analysis via the interactive UI or directly from the terminal.

### Local Setup & Launch

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Launch the Streamlit Journey Inspector
streamlit run src/ai_search_journey/app.py
```

*(Note: V2 runs strictly in-memory (`Session only`) and does not require BigQuery or external database setup).*

### CLI Demonstration

You can also run the standalone SJO terminal demo script:

```bash
python scripts/demo_journey_v2.py
```

### Test Scenario & Prompt

In the Streamlit Journey Inspector (or preset dropdown), execute the search journey for:

```text
Find a coffee shop near Geekdom San Antonio for 6 people to work together, preferably quiet, and open after 8 PM.
```

Click **🚀 Run Search Journey**.

### What to Inspect in the UI

Open the **Journey Analysis [V2]** tab to inspect the complete SJO transition matrix:

1. **📈 Search Journey Progression Summary**:
   - Compares initial Places Retrieval Position (`#1`, `#3`, etc.), Evidence-Enriched Position, and Final Recommendation Position for each candidate.
   - Highlights rank movement badges (`▲ +2`, `▼ -1`, `● Unchanged`) with final scores.
2. **🧭 Retrieval Provenance by Query**:
   - Table detailing exact fan-out tasks (`F1`, `F2`), query texts, and result set positions where each candidate was discovered.
3. **🔍 Ranked Candidate Deep-Dive**:
   - **Movement Explanation**: Deterministic explanations of why a venue rose or dropped (e.g. *"Moved up +2 positions due to confirmed late-night operating hours and high proximity score"*).
   - **Transparent Score Breakdown**: Inspect exact point contributions from Hard Constraints (+25.0), Preferences (+10.0), Proximity Points (+8.4), Quality Points (+6.5), and Penalties.
   - **Retrieval Occurrences & Reasons**: Full query audit for every candidate.
