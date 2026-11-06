# Contributing to AI Search Journey Lab

Thanks for helping improve AI Search Journey Lab! This guide gets you from clone to a clean Pull Request (PR) as quickly as possible.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Running Locally](#running-locally)
4. [Testing](#testing)
5. [Linting with Ruff](#linting-with-ruff)
6. [Type Checking with mypy](#type-checking-with-mypy)
7. [Docker Workflow](#docker-workflow)
8. [Branch and Commit Guidance](#branch-and-commit-guidance)
9. [Pull Request Expectations](#pull-request-expectations)
10. [Updating Documentation](#updating-documentation)
11. [Troubleshooting](#troubleshooting)

## Prerequisites

- Python 3.12 or newer
- Git
- Docker (optional, needed only for the Docker and observability workflows)
- A Gemini API key and a Google Maps API key (needed only to run the app against live services; the test suite does not require real keys)

## Environment Setup

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/<your-username>/ai-search-journey-lab.git
cd ai-search-journey-lab

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install the package with development dependencies
pip install -e ".[bigquery,v4-agent,dev]"

# 4. Create your local environment file
cp .env.example .env

# 5. Verify your setup with environment diagnostics
ai-search-journey-lab doctor
```

Edit `.env` and add your keys:

```
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
GOOGLE_MAPS_API_KEY="YOUR_GOOGLE_MAPS_API_KEY"
```

> Never commit `.env` or any real API key.

## Running Locally

Run the Streamlit Journey Inspector in-memory (no Docker, no database):

```bash
streamlit run src/ai_search_journey/app.py
```

Or start the app together with the local observability stack (needs Docker):

```bash
python scripts/run_app_locally.py
```

Individual pipeline stages can be explored with the CLI demos in `scripts/` (for example `scripts/demo_ranking.py`).

## Testing

Run the full test suite before every PR:

```bash
python -m pytest -v
```

- Add or update tests in `tests/` for every behaviour change.
- Tests should not call live Google or Gemini services; mock external calls.

## Linting with Ruff

```bash
python -m ruff check .
```

Fix reported issues before pushing. Many can be fixed automatically with `python -m ruff check . --fix`.

## Type Checking with mypy

```bash
python -m mypy src
```

New code in `src/` should be fully type-annotated and pass without new errors.

## Docker Workflow

Build and run the production image locally:

```bash
docker build -t ai-search-journey-lab:local .

docker run --rm \
  -p 8080:8080 \
  --env-file .env \
  ai-search-journey-lab:local
```

Open `http://localhost:8080`, and check container health with:

```bash
curl http://localhost:8080/_stcore/health
```

To run the optional local observability stack (Grafana, Prometheus, Tempo) on its own:

```bash
docker compose -f docker-compose.observability.yml up -d
```

## Branch and Commit Guidance

- Fork the repository and branch from `main`.
- Use descriptive branch names with a prefix:
  - `feature/<short-description>` for new capabilities
  - `fix/<short-description>` for bug fixes
  - `docs/<short-description>` for documentation-only changes
- Keep each branch focused on a single issue or change.
- Write clear, imperative commit messages, for example `Add CONTRIBUTING.md with setup guide`.
- Reference the issue in your commit or PR (for example `Closes #22`).

## Pull Request Expectations

Before opening a PR, confirm that:

- [ ] `python -m pytest -v` passes
- [ ] `python -m ruff check .` passes
- [ ] `python -m mypy src` passes
- [ ] New or changed behaviour has tests
- [ ] Documentation is updated where needed
- [ ] No secrets, `.env` files, or generated artifacts are included

In your PR description:

- Link the issue it resolves (`Closes #<number>`).
- Summarise what changed and why.
- Include screenshots for any user interface (UI) change.
- Keep the PR small and focused; open separate PRs for unrelated changes.

Maintainers may request changes. Please respond in the PR thread and push updates to the same branch.

## Updating Documentation

Update documentation in the same PR as the code change when you:

- add or change a feature, command, or environment variable (update `README.md`)
- change setup, testing, or deployment steps (update this file and `README.md`)
- add observability or architecture details (update the relevant file in `docs/`)

Documentation tips:

- Keep commands copy-pasteable and test them before submitting.
- Match the existing tone and heading structure.
- Check that all relative links still resolve.

## Troubleshooting

Run the doctor command to identify configuration or dependency issues:

```bash
ai-search-journey-lab doctor
```

Having trouble with setup, Docker, or the observability stack? See the
[Dockerized Observability Guide](docs/bonus-b-dockerized-observability.md), which includes troubleshooting steps.

If you are still stuck, open a GitHub issue with:

- your operating system and Python version
- the exact command you ran
- the full error output (with any secrets removed)

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
