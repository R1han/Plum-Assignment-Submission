# Component Contracts

Precise interfaces for every significant component. Types refer to the
Pydantic models in `backend/app/models/` — each contract here is enforced at
runtime by validation, so "another engineer could reimplement any component
against these tables" is literally true: the test suite would tell them when
they're done.

Conventions: all amounts are INR floats; all dates are ISO `date`s; every
component that participates in a claim appends `TraceStep` records to the
shared trace.

---

## 1. Policy Loader — `app/policy/loader.py`

| | |
|---|---|
| **Input** | Path to a `policy_terms.json` file (defaults to `settings.policy_file`). |
| **Output** | `Policy` — typed view of the entire policy: coverage, categories, waiting periods, exclusions, pre-auth, network hospitals, submission rules, document requirements, fraud thresholds, member roster. Helper methods: `get_member`, `get_category`, `get_document_requirement`, `member_join_date` (dependents inherit primary's), `is_network_hospital` (bidirectional substring). |
| **Errors** | `FileNotFoundError` (missing file), `pydantic.ValidationError` (schema mismatch). Both are startup-fatal by design — no claim may be processed without a valid policy. |

## 2. Extraction Service — `app/agents/extraction.py`

| | |
|---|---|
| **Input** | `DocumentInput` — exactly one of two shapes: fixture (`actual_type` + optional `quality`/`content`/`patient_name_on_doc`) or upload (`file_data` base64 + `media_type`). |
| **Output** | `ExtractedDocument` — `doc_type` (enum), `quality` (GOOD/PARTIAL/UNREADABLE), `content: DocumentContent` (patient/doctor/diagnosis/medicines/line_items/total/...), `extraction_confidence` [0,1], `source` ("fixture"\|"vision"), `warnings: list[str]`. UNREADABLE documents carry empty content and confidence 0. |
| **Errors** | `ExtractionError` — missing API key for an upload, API failure, undecodable file, or input with neither shape. Caught per-document by the orchestrator (degradation, not crash). |
| **Models** | Vision path: `claude-sonnet-4-6`, structured output (`messages.parse`), single call per document classifying type + quality + extracting fields. |

## 3. Document Verification Agent — `app/agents/document_verification.py`

| | |
|---|---|
| **Input** | `ClaimSubmission`, `list[ExtractedDocument]`, trace list. |
| **Output** | `VerificationResult` — `ok: bool`, `issues: list[DocumentIssue]` (`code` ∈ MISSING_DOCUMENT \| WRONG_DOCUMENT_TYPE \| UNREADABLE_DOCUMENT \| PATIENT_MISMATCH, member-facing `message`, `file_id`, `expected`, `found`), `patient_name` (consensus across docs). |
| **Behavior** | Checks in order: required types for the category (from policy `document_requirements`), usability, cross-document patient consistency, patient-on-roster (member or covered dependent). Name comparison is title-stripped token-set match. `ok=False` ⇒ pipeline stops before adjudication. |
| **Usability gate** | A document is blocked as UNREADABLE_DOCUMENT when any of: `quality == UNREADABLE`; `extraction_confidence < 0.6` (the model's PARTIAL label is not trusted on its own); or — vision-extracted bills only — no amounts could be read, or quality is PARTIAL with warnings naming amounts/totals. Rationale: a payout cannot be backed by amounts the extractor itself flagged as unreliable. Fixture documents are exempt from the bill-amount rules (they assert their own ground truth). |
| **Errors** | Never raises on claim data. Missing requirements config → ERROR trace step, no issues. |

## 4. Rules Engine — `app/engine/rules.py`

| | |
|---|---|
| **Input** | `ClaimSubmission`, `ClaimFacts` (consolidated extraction view), trace list. Constructor takes `Policy` + optional `Classifier`. |
| **Output** | `AdjudicationResult` — `status` (APPROVED/PARTIAL/REJECTED/MANUAL_REVIEW), `rejection_reasons: list[RejectionReason]` (machine-readable enum), `reasons: list[str]` (human), `line_items: list[LineItemVerdict]`, `financial: FinancialBreakdown`, `member_message`, `classifier_certainty` ("exact"\|"keyword"\|"llm" — weakest used on the path). |
| **Check order** | member eligibility → submission rules → category coverage → exclusions → waiting periods → pre-auth → line-item screening → per-claim cap (`max(global limit, category sub-limit)` on covered amount) → sub-limit/annual caps → financial. First terminal failure wins; the rest are traced SKIPPED. |
| **Financial invariant** | Network discount **before** co-pay, both on the covered amount; every intermediate figure in the breakdown. |
| **Errors** | Never raises on claim data — invalid states are REJECTED/MANUAL_REVIEW outcomes with traced reasons. |

## 5. Classifier — `app/engine/matching.py` + `app/agents/classifiers.py`

| | |
|---|---|
| **Input** | Free text (diagnosis / treatment / line-item description) + the relevant policy list. |
| **Output** | `MatchResult` — `matched: bool`, `rule` (the policy entry, verbatim), `certainty` ("exact" \| "keyword" \| "llm" \| "none"). Procedure variant returns `("covered"\|"excluded"\|"unknown", MatchResult)`. |
| **Behavior** | Tier 1 deterministic: normalized word-boundary phrase matching, synonym maps keyed to the policy's own vocabulary. Tier 2 (`LLMClassifier`, `claude-opus-4-8`, structured output): engages only when tier 1 misses; result must quote a verbatim list entry or it is discarded. Per-process memoization. Disabled when `OFFLINE_MODE` or no API key. |
| **Errors** | LLM failures never propagate — recorded in `.failures`, return "no match". |

## 6. Fraud Agent — `app/engine/fraud.py`

| | |
|---|---|
| **Input** | `ClaimSubmission` (with `claims_history`), extraction warnings, trace list. |
| **Output** | `FraudAssessment` — `flagged`, `route_manual_review`, `signals: list[str]` (specific, e.g. "4 claims from this member on 2024-10-30 ... CLM_0081 ₹1200 ..."). |
| **Thresholds** | All from policy `fraud_thresholds`: same-day count, monthly count, `auto_manual_review_above`, plus document-alteration markers from extraction warnings. |
| **Invariant** | Fraud never rejects — it only routes APPROVED/PARTIAL to MANUAL_REVIEW. |

## 7. Confidence Scorer — `app/engine/confidence.py`

| | |
|---|---|
| **Input** | `extraction_confidence` [0,1], `classifier_certainty`, `component_failures` count, `warning_count`. |
| **Output** | `ConfidenceReport` — `score` ∈ [0.05, 0.95] and itemized `deductions` (traced). |
| **Formula** | base 0.95; −(1−extraction)·0.20; certainty keyword −0.02 / llm −0.08; −0.20 per component failure; −0.02 per warning (cap −0.10). Pure function — same inputs, same score. |

## 8. Pipeline Orchestrator — `app/graph/pipeline.py`

| | |
|---|---|
| **Input** | `ClaimSubmission` (+ optional claim_id). |
| **Output** | `ClaimOutcome` — `outcome_type` (DECISION \| DOCUMENT_ISSUE), `decision: Decision \| None`, `document_issues`, `degraded`, `component_failures`, full ordered `trace`. |
| **Graph** | intake → extract → verify →(issues)→ finalize; (clean)→ adjudicate → fraud_check → finalize. |
| **Resilience contract** | A node exception becomes `ComponentFailure` + ERROR trace step; the run continues. Criticality table in ARCHITECTURE.md. `simulate_component_failure` raises in fraud_check. |
| **Errors** | `run()` does not raise on any claim content; only programming errors in finalize itself could surface (none known; eval TC011 guards the path). |

## 9. Repository — `app/db/repository.py`

| | |
|---|---|
| **Input** | (`ClaimSubmission`, `ClaimOutcome`) pairs; member ids for history. |
| **Output** | `ClaimRecord` rows (summary columns + outcome/submission JSON, file bytes excluded); `list[HistoricalClaim]` for fraud checks; `merge_history` dedupes provided vs stored by claim_id. |
| **Errors** | SQLAlchemy exceptions propagate to the API layer (500). |

## 10. HTTP API — `app/api/main.py`

| Endpoint | Input | Output | Errors |
|---|---|---|---|
| `POST /api/claims` | `ClaimSubmission` JSON | `ClaimOutcome` | 422 invalid payload |
| `POST /api/claims/upload` | multipart form: member_id, policy_id, claim_category, treatment_date, claimed_amount, hospital_name?, files[] | `ClaimOutcome` | 413 file >5MB (Claude API image limit), 422 invalid fields |
| `GET /api/claims` | — | claim summaries (newest first) | — |
| `GET /api/claims/{id}` | claim id | `{submission, outcome}` with full trace | 404 unknown id |
| `GET /api/policy` | — | policy summary for the UI | — |
| `GET /health` | — | `{"status": "ok"}` | — |

Behavior: stored member history is merged into every submission's
`claims_history` before the pipeline runs, so DB-accumulated same-day claims
trigger the fraud route in the live system exactly as fixtures do in evals.

## 11. Eval Harness — `backend/evals/`

| | |
|---|---|
| **Input** | `data/test_cases.json` (the 12 official cases). |
| **Output** | `CaseResult` per case (outcome + named expectation checks); `report.md` with decision, expectation checks, and full trace per case. Exit code 0 iff 12/12. |
| **Invariant** | Runs the real pipeline with the deterministic classifier tier only — reproducible offline, no API key. A pipeline crash is a failed check, not a harness error. |
