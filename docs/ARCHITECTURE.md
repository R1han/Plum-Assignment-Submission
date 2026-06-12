# Architecture

Health insurance claims processing system for the Plum AI Engineer assignment.

## System overview

```
                         ┌─────────────────────────────────────────────────┐
 Next.js UI ── HTTP ──▶  │ FastAPI                                         │
 (Vercel)                │  POST /api/claims          (structured JSON)    │
                         │  POST /api/claims/upload   (multipart files)    │
                         │  GET  /api/claims[/id]     (review + trace)     │
                         └───────────────┬─────────────────────────────────┘
                                         │ ClaimSubmission
                                         ▼
              ┌─────────────────────────────────────────────────────┐
              │ LangGraph pipeline (one state machine per claim)    │
              │                                                     │
              │  intake ─▶ extract ─▶ verify ──issues──▶ finalize   │
              │                          │                    ▲     │
              │                        clean                  │     │
              │                          ▼                    │     │
              │                     adjudicate ─▶ fraud_check ┘     │
              └──────────┬──────────────────┬───────────────────────┘
                         │                  │
              ┌──────────▼─────────┐  ┌─────▼──────────────┐
              │ Claude API         │  │ policy_terms.json  │
              │  Sonnet 4.6 vision │  │ (single source of  │
              │  Opus 4.8 fallback │  │  policy truth)     │
              │  classification    │  └────────────────────┘
              └────────────────────┘
                         │
              ┌──────────▼─────────┐
              │ SQLite             │  claims + decisions + full traces
              └────────────────────┘
```

## Components

| Component | Module | Responsibility |
|---|---|---|
| Policy loader | `app/policy/loader.py` | Parse + validate `policy_terms.json` into typed models. **No policy value is hardcoded anywhere else.** |
| Extraction service | `app/agents/extraction.py` | One interface, two adapters: `FixtureAdapter` (structured test input) and `VisionExtractor` (Claude Sonnet 4.6 on uploaded images/PDFs). |
| Document verification | `app/agents/document_verification.py` | The early gate: required-document check, readability check, cross-document patient consistency, roster membership. Stops the pipeline with member-facing, actionable messages. |
| Rules engine | `app/engine/rules.py` | Deterministic adjudication: eligibility, waiting periods, exclusions, pre-auth, limits, line-item screening, financial math. |
| Classifier (2-tier) | `app/engine/matching.py` + `app/agents/classifiers.py` | Tier 1: deterministic keyword/synonym matching derived from the policy file. Tier 2: Claude Opus 4.8 fallback for fuzzy text tier 1 can't resolve. |
| Fraud detection | `app/engine/fraud.py` | Same-day/monthly frequency, high-value threshold, document-alteration markers. Routes to MANUAL_REVIEW — never auto-rejects. |
| Confidence scoring | `app/engine/confidence.py` | Deterministic, documented formula combining extraction quality, classifier certainty, component failures, and warnings. |
| Orchestrator | `app/graph/pipeline.py` | LangGraph state machine; per-node resilience wrappers; builds the final outcome + trace. |
| Persistence | `app/db/` | SQLite via SQLAlchemy; summary columns + full outcome JSON; feeds claim history into fraud checks. |
| API | `app/api/main.py` | Claim submission (JSON + multipart), decision retrieval, policy summary. |
| UI | `frontend/` | Next.js: submission form (file upload + demo scenarios), decisions list, decision review with full trace timeline. |

## Key design decisions

### 1. Deterministic rules core, LLMs only at the edges

The decision itself is computed by plain Python evaluating the policy file.
LLMs are used for exactly two jobs: **reading documents** (vision extraction)
and **classifying fuzzy text** (does "Personalised Diet and Nutrition Program"
fall under "Obesity and weight loss programs"?).

Why: money math and dates must be exact and reproducible. An LLM that
"reasons over the policy" produces narrative traces that cannot be audited
check-by-check, drifts run-to-run, and fails the eval's exact amounts
(₹3,240 on TC010 leaves no rounding slack). With the deterministic core, the
12-case eval is **exactly reproducible offline** — the report in
`backend/evals/report.md` regenerates byte-identical with no API key.

**Considered and rejected:** a single Opus "adjudicator agent" with the
policy JSON in context. Rejected because: non-deterministic outcomes on
boundary amounts, no per-check trace, cost/latency per claim ~100x higher,
and hallucination risk on arithmetic. The interview-friendly version of this
trade-off: *LLMs read and classify; code decides.*

### 2. Two-tier classification with LLM fallback

Tier 1 is keyword/synonym matching (`matching.py`) — synonyms expand the
policy's own vocabulary (HTN → hypertension) and are word-boundary matched
("hernia" must not match "Disc Herniation"; that bug was caught by TC007's
test). Tier 2 (Claude) engages only when tier 1 finds nothing, and an LLM
match lowers decision confidence (-0.08 vs -0.02 for keyword), making the
fuzziness visible. LLM failures degrade to "no match" — they never crash
adjudication.

### 3. Dual-adapter document ingestion

`test_cases.json` supplies pre-structured document content; the real UI
uploads images. Both flow through one `ExtractionService` interface into the
same `ExtractedDocument` shape, so verification/adjudication are identical
for both paths and the eval exercises the *real* pipeline, not a test double.

### 4. LangGraph for orchestration, but the trace is ours

LangGraph gives the explicit state machine (and the multi-agent structure)
— but the audit trace is **not** the framework's internals. Every node
appends typed `TraceStep` records (component, check, status, detail, data)
to an additive-reducer state channel. The trace is the system of record for
explainability: the ops answer to "why did this claim get this decision" is
reconstructable from the trace alone.

### 5. Graceful degradation by construction

Every node runs inside a `@resilient` wrapper that converts unhandled
exceptions into `ComponentFailure` records + ERROR trace steps, then lets the
graph continue. Failure semantics are explicit per node:

| Node | Criticality | On failure |
|---|---|---|
| extract | non-critical | continue with the documents that did extract |
| verify | non-critical | continue unverified (flagged) |
| adjudicate | critical | decision = MANUAL_REVIEW (never a crash) |
| fraud_check | non-critical | skip fraud screen (flagged) |

Each failure costs -0.20 confidence and sets `manual_review_recommended`.
TC011's `simulate_component_failure` flag raises inside `fraud_check` — chosen
as the injection point because it demonstrates a *non-critical* failure: the
claim still gets a correct APPROVED decision, with the failure visible in the
output and confidence reduced (0.75 vs 0.95 clean).

### 6. Fraud routes to humans, never auto-rejects

A fraud signal on an otherwise-approvable claim produces MANUAL_REVIEW with
the specific signals in the output (TC009). False-positive fraud rejection is
a member-trust disaster; a human gate is the correct cost.

## Documented assumptions (ambiguities in the spec)

1. **Category sub-limit vs per-claim limit.** TC006 approves ₹8,000 on a
   ₹12,000 dental claim despite the global ₹5,000 per-claim limit, while
   TC008 rejects ₹7,500 consultation against that same limit. The
   interpretation that satisfies both: the effective per-claim cap is
   `max(global per_claim_limit, category sub_limit)`, applied to the covered
   amount after line-item screening. The consultation sub-limit (₹2,000)
   additionally caps consultation-fee line items only — TC010 approves ₹3,240
   on a ₹4,500 consultation claim, so the sub-limit cannot cap whole claims.
2. **Submission date.** Test fixtures carry 2024 treatment dates with no
   submission date; evaluating the 30-day deadline against the wall clock
   would reject every fixture. `submission_date` defaults to
   `treatment_date` when absent; real uploads set it to today.
3. **Exclusions precede waiting periods.** Morbid obesity (TC012) matches
   both an exclusion and a waiting-period condition; exclusion wins because a
   permanent exclusion dominates a temporary wait.
4. **Unknown line items default to covered, flagged.** In list-governed
   categories (dental/vision), an item on neither list is paid but flagged in
   the trace — conservative payout denials belong to ops policy, not code.
5. **Patient names.** Token-set comparison tolerant of titles and order
   ("Mr. Rajesh Kumar" == "Rajesh Kumar"); dependents inherit the primary
   member's join date for waiting periods.

## Failure modes

- **Claude API down / no key:** fixtures and the entire rules engine work
  offline; uploads fail extraction with a clear ExtractionError, recorded as
  a component failure (degraded outcome), not a 500.
- **Malformed submission:** 422 with field-level pydantic errors at the API
  boundary; the pipeline never sees invalid input.
- **Pipeline bug:** the resilience wrappers convert it to MANUAL_REVIEW (if
  adjudication) or a flagged degraded decision; the eval's TC011 pins this.
- **DB unavailability:** the only true 500 path (persistence is the system of
  record); processing itself has no DB dependency until save.

## Scaling to 10x (and beyond)

Current shape: synchronous in-process pipeline, SQLite, one worker. At 75K
claims/year (~10/hour peak) this is comfortably over-provisioned. At 10x–100x:

1. **Queue the pipeline.** The LangGraph invocation moves behind a task queue
   (Celery/SQS); `POST /api/claims` returns `202 + claim_id` immediately and
   the UI polls `GET /api/claims/{id}` (the endpoint shape already supports
   this — only the submission endpoint changes).
2. **Postgres.** Swap `DATABASE_URL`; SQLAlchemy models are already
   dialect-neutral. JSONB for outcome/trace, indexes on (member_id, date) for
   the fraud history query.
3. **Parallelize extraction.** Documents within a claim extract concurrently
   (async Anthropic client); vision is the latency bottleneck (~5-15s/doc).
4. **Batch + cache LLM calls.** Classifier results are already memoized
   per-process; move the cache to Redis keyed on (text, policy version).
   Non-urgent claims can use the Batches API at 50% cost.
5. **Stateless workers.** All state lives in the DB + policy file; workers
   scale horizontally with zero coordination.
6. **Policy versioning.** Multiple policies/insurers = a `policies` table and
   per-claim policy resolution — the loader already takes a path/payload, and
   nothing else reads the file directly.

What I would change with more time: async pipeline end-to-end (the Anthropic
calls are the only real I/O); an ops console with decision override + audit;
golden-set regression evals on extraction (mock document images with known
ground truth); and structured logging/OTel spans mirroring the trace steps.
