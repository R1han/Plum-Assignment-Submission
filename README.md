# Plum Claims Processing — AI Engineer Assignment

An automated health insurance claims adjudication system: members submit
medical documents, a multi-agent pipeline verifies them, extracts structured
data, adjudicates against the policy, and produces an explainable decision
with a full audit trace.

**Eval result: 12/12 official test cases pass** — see
[backend/evals/report.md](backend/evals/report.md).

## How it works (30 seconds)

```
submit ─▶ intake ─▶ extract (Claude vision / fixtures)
                       ─▶ verify documents ──issues──▶ stop with actionable message
                       ─▶ adjudicate (deterministic rules from policy_terms.json,
                                      LLM fallback only for fuzzy text)
                       ─▶ fraud signals ─▶ decision + confidence + full trace
```

Design principle: **LLMs read and classify; code decides.** Money math,
waiting periods, and limits are deterministic and fully traced. Details and
trade-offs: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · component
interfaces: [docs/CONTRACTS.md](docs/CONTRACTS.md).

## Run locally

Backend (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY for document uploads;
                                # everything else works without it
.venv/bin/uvicorn app.api.main:app --port 8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Or both with Docker:

```bash
ANTHROPIC_API_KEY=sk-ant-... docker compose up --build
```

## Tests and evals

```bash
cd backend
.venv/bin/python -m pytest tests/        # 64 tests
.venv/bin/python -m evals.run_evals      # 12 official cases -> evals/report.md
```

Both run fully offline (no API key): the eval uses the deterministic
classifier tier, so the report is exactly reproducible.

## Repository map

```
backend/
  app/
    models/        domain models (claim, decision, policy, extraction)
    policy/        policy_terms.json loader — single source of policy truth
    engine/        deterministic core: rules, financial, fraud, confidence, matching
    agents/        LLM-adjacent: vision extraction, doc verification, classifiers
    graph/         LangGraph pipeline + state (trace, degradation)
    db/            SQLite persistence (claims + full traces)
    api/           FastAPI endpoints
  evals/           eval harness + generated report (12/12)
  tests/           pytest suite
frontend/          Next.js UI: submission, decisions list, trace review
docs/              ARCHITECTURE.md, CONTRACTS.md
```

## Deployment

- **API**: Render (Blueprint in `render.yaml`) or any Docker host. Set
  `ANTHROPIC_API_KEY` and `CORS_ORIGINS`.
- **UI**: Vercel — root directory `frontend`, env
  `NEXT_PUBLIC_API_URL=<api url>`.

## Assignment deliverables

| Deliverable | Where |
|---|---|
| Working system + UI | this repo; run instructions above |
| Architecture document | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Component contracts | [docs/CONTRACTS.md](docs/CONTRACTS.md) |
| Eval report (12 cases, full traces) | [backend/evals/report.md](backend/evals/report.md) |
| Demo video | _link to be added_ |
