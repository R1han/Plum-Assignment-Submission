# Eval Report — 12 Official Test Cases

**Result: 12/12 cases match the expected outcome.**

Pipeline configuration: deterministic classifier tier only (no LLM calls), so this report is exactly reproducible: `python -m evals.run_evals`. The LLM fallback tier engages only on fuzzy text the keyword tier cannot resolve, which none of the official fixtures require.

| Case | Name | Expected | Got | Match |
|------|------|----------|-----|-------|
| TC001 | Wrong Document Uploaded | no decision (stop early) | stopped early (document issue) | ✅ |
| TC002 | Unreadable Document | no decision (stop early) | stopped early (document issue) | ✅ |
| TC003 | Documents Belong to Different Patients | no decision (stop early) | stopped early (document issue) | ✅ |
| TC004 | Clean Consultation — Full Approval | APPROVED | APPROVED, ₹1350 | ✅ |
| TC005 | Waiting Period — Diabetes | REJECTED | REJECTED | ✅ |
| TC006 | Dental Partial Approval — Cosmetic Exclusion | PARTIAL | PARTIAL, ₹8000 | ✅ |
| TC007 | MRI Without Pre-Authorization | REJECTED | REJECTED | ✅ |
| TC008 | Per-Claim Limit Exceeded | REJECTED | REJECTED | ✅ |
| TC009 | Fraud Signal — Multiple Same-Day Claims | MANUAL_REVIEW | MANUAL_REVIEW | ✅ |
| TC010 | Network Hospital — Discount Applied | APPROVED | APPROVED, ₹3240 | ✅ |
| TC011 | Component Failure — Graceful Degradation | APPROVED | APPROVED, ₹4000 | ✅ |
| TC012 | Excluded Treatment | REJECTED | REJECTED | ✅ |

---

## TC001 — Wrong Document Uploaded

**No decision — stopped early with document issues:**

- **MISSING_DOCUMENT**: Your consultation claim requires both a prescription and a hospital bill. You uploaded 2 prescriptions, but no hospital bill was included. Please upload the hospital bill for your treatment on 2024-11-01 and resubmit.

**Expectation checks:**

- ✅ stops before decision — outcome_type=DOCUMENT_ISSUE, decision=None
- ✅ names uploaded doc type (prescription) — your consultation claim requires both a prescription and a hospital bill. you uploaded 2 prescriptions, but no hospital bill was included. please upload the hospital bill for your treatment on 2024-11
- ✅ names required doc type (hospital bill) — your consultation claim requires both a prescription and a hospital bill. you uploaded 2 prescriptions, but no hospital bill was included. please upload the hospital bill for your treatment on 2024-11

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC001 received: member EMP001, category CONSULTATION, amount ₹1500, 2 document(s), treatment date 2024-11-01. |
| 2 | extraction | extract_F001 | PASS | F001: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F002 | PASS | F002: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | FAIL | Missing required document(s): HOSPITAL_BILL. Uploaded: 2 prescriptions. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | finalize | outcome | INFO | Stopped before adjudication: 1 document issue(s) returned to the member. No decision made. |

---

## TC002 — Unreadable Document

**No decision — stopped early with document issues:**

- **UNREADABLE_DOCUMENT** (F004): The pharmacy bill you uploaded (blurry_bill.jpg) could not be read reliably — the image is too blurry or unclear. Please take a clear, well-lit photo of the pharmacy bill and re-upload just that document. The rest of your claim is fine and will be processed once we can read it.

**Expectation checks:**

- ✅ stops before decision — outcome_type=DOCUMENT_ISSUE, decision=None
- ✅ identifies the unreadable pharmacy bill — issues=[('UNREADABLE_DOCUMENT', 'F004')]
- ✅ asks for re-upload, not rejection — the pharmacy bill you uploaded (blurry_bill.jpg) could not be read reliably — the image is too blurry or unclear. please take a clear, well-lit photo of the pharmacy bill and re-upload just that docum

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC002 received: member EMP004, category PHARMACY, amount ₹800, 2 document(s), treatment date 2024-10-25. |
| 2 | extraction | extract_F003 | PASS | F003: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F004 | PASS | F004: PHARMACY_BILL (UNREADABLE, source=fixture, confidence=0); warnings: document unreadable; no fields extracted |
| 4 | document_verification | required_documents | PASS | All required documents present for PHARMACY: PRESCRIPTION, PHARMACY_BILL. |
| 5 | document_verification | document_readability | FAIL | Document F004 (PHARMACY_BILL) is not usable: the image is too blurry or unclear. |
| 6 | finalize | outcome | INFO | Stopped before adjudication: 1 document issue(s) returned to the member. No decision made. |

---

## TC003 — Documents Belong to Different Patients

**No decision — stopped early with document issues:**

- **PATIENT_MISMATCH** (F006): The documents you uploaded belong to different patients: the prescription (prescription_rajesh.jpg) is for 'Rajesh Kumar', but the hospital bill (bill_arjun.jpg) is for 'Arjun Mehta'. All documents in one claim must belong to the same patient. Please check your files and re-upload the correct documents.

**Expectation checks:**

- ✅ stops before decision — outcome_type=DOCUMENT_ISSUE, decision=None
- ✅ surfaces both patient names — The documents you uploaded belong to different patients: the prescription (prescription_rajesh.jpg) is for 'Rajesh Kumar', but the hospital bill (bill_arjun.jpg) is for 'Arjun Mehta'. All documents in

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC003 received: member EMP001, category CONSULTATION, amount ₹1500, 2 document(s), treatment date 2024-11-01. |
| 2 | extraction | extract_F005 | PASS | F005: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F006 | PASS | F006: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for CONSULTATION: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_consistency | FAIL | Patient mismatch: 'Rajesh Kumar' on F005 vs 'Arjun Mehta' on F006. |
| 7 | finalize | outcome | INFO | Stopped before adjudication: 1 document issue(s) returned to the member. No decision made. |

---

## TC004 — Clean Consultation — Full Approval

- **Status:** APPROVED
- **Approved amount:** ₹1350
- **Confidence:** 0.95
- **Member message:** Your claim is approved for ₹1350.
- **Line items:**
  - Consultation Fee (₹1000): covered — no procedure restrictions for this category
  - CBC Test (₹300): covered — no procedure restrictions for this category
  - Dengue NS1 Test (₹200): covered — no procedure restrictions for this category
- **Financial:** claimed ₹1500 → covered ₹1500 → discount ₹0 → co-pay ₹150 → payable ₹1350

**Expectation checks:**

- ✅ decision == APPROVED — got APPROVED
- ✅ approved_amount == 1350 — got 1350.0
- ✅ confidence above 0.85 — got 0.95

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC004 received: member EMP001, category CONSULTATION, amount ₹1500, 2 document(s), treatment date 2024-11-01. |
| 2 | extraction | extract_F007 | PASS | F007: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F008 | PASS | F008: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for CONSULTATION: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_on_roster | PASS | Patient 'Rajesh Kumar' matches the membership of EMP001. |
| 7 | document_verification | patient_consistency | PASS | All documents belong to the same patient. Patient: Rajesh Kumar. |
| 8 | rules_engine | member_exists | PASS | Member EMP001 (Rajesh Kumar) found on roster. |
| 9 | rules_engine | policy_active | PASS | Treatment date 2024-11-01 within policy period. |
| 10 | rules_engine | minimum_claim_amount | PASS | Claimed ₹1500 ≥ minimum ₹500. |
| 11 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 12 | rules_engine | category_covered | PASS | Category CONSULTATION is covered (sub-limit ₹2000, co-pay 10%). |
| 13 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 14 | rules_engine | initial_waiting_period | PASS | 214 days since cover start ≥ 30-day initial wait. |
| 15 | rules_engine | condition_waiting_period | PASS | Diagnosis does not map to any condition-specific waiting period. |
| 16 | rules_engine | pre_authorization | PASS | No pre-authorization requirement applies to this category. |
| 17 | rules_engine | line_item_screening | PASS | Consultation Fee (₹1000): covered — no procedure restrictions for this category |
| 18 | rules_engine | line_item_screening | PASS | CBC Test (₹300): covered — no procedure restrictions for this category |
| 19 | rules_engine | line_item_screening | PASS | Dengue NS1 Test (₹200): covered — no procedure restrictions for this category |
| 20 | rules_engine | per_claim_limit | PASS | Payable ₹1500 ≤ per-claim limit ₹5000. |
| 21 | rules_engine | category_sub_limit | PASS | Primary service charges within category sub-limit ₹2000. |
| 22 | rules_engine | annual_opd_limit | PASS | YTD ₹5000 + this claim within the annual OPD limit ₹50000. |
| 23 | rules_engine | network_hospital | INFO | Hospital 'City Clinic, Bengaluru' is NOT in the network list. |
| 24 | rules_engine | financial_computation | PASS | Co-pay (10%) applied on ₹1500 = ₹150 deducted. Final payable: ₹1350. |
| 25 | fraud_detection | fraud_signals | PASS | No fraud signals: same-day, monthly, high-value, and document-alteration checks all clear. |
| 26 | finalize | outcome | INFO | Decision: APPROVED, approved ₹1350, confidence 0.95 (no deductions). |

---

## TC005 — Waiting Period — Diabetes

- **Status:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.93
- **Member message:** Claims for diabetes have a 90-day waiting period. Your cover started on 2024-09-01, so you will be eligible for diabetes-related claims from 2024-11-30.
- **Rejection reasons:** WAITING_PERIOD

**Expectation checks:**

- ✅ decision == REJECTED — got REJECTED
- ✅ rejection_reasons include ['WAITING_PERIOD'] — got ['WAITING_PERIOD']
- ✅ states the eligibility date (2024-11-30) — claims for diabetes have a 90-day waiting period. your cover started on 2024-09-01, so you will be eligible for diabetes-related claims from 2024-11-30. claims for diabetes have a 90-day waiting perio

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC005 received: member EMP005, category CONSULTATION, amount ₹3000, 2 document(s), treatment date 2024-10-15. |
| 2 | extraction | extract_F009 | PASS | F009: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F010 | PASS | F010: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for CONSULTATION: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_on_roster | PASS | Patient 'Vikram Joshi' matches the membership of EMP005. |
| 7 | document_verification | patient_consistency | PASS | All documents belong to the same patient. Patient: Vikram Joshi. |
| 8 | rules_engine | member_exists | PASS | Member EMP005 (Vikram Joshi) found on roster. |
| 9 | rules_engine | policy_active | PASS | Treatment date 2024-10-15 within policy period. |
| 10 | rules_engine | minimum_claim_amount | PASS | Claimed ₹3000 ≥ minimum ₹500. |
| 11 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 12 | rules_engine | category_covered | PASS | Category CONSULTATION is covered (sub-limit ₹2000, co-pay 10%). |
| 13 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 14 | rules_engine | initial_waiting_period | PASS | 44 days since cover start ≥ 30-day initial wait. |
| 15 | rules_engine | condition_waiting_period | FAIL | Diagnosis 'Type 2 Diabetes Mellitus' maps to condition 'diabetes' (90-day wait); member covered only 44 days (joined 2024-09-01). |
| 16 | rules_engine | pre_authorization | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 17 | rules_engine | per_claim_limit | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 18 | rules_engine | line_item_screening | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 19 | fraud_detection | fraud_signals | PASS | No fraud signals: same-day, monthly, high-value, and document-alteration checks all clear. |
| 20 | finalize | outcome | INFO | Decision: REJECTED, approved ₹0, confidence 0.93 (deductions: -0.02: weakest text-match certainty 'keyword'). |

---

## TC006 — Dental Partial Approval — Cosmetic Exclusion

- **Status:** PARTIAL
- **Approved amount:** ₹8000
- **Confidence:** 0.93
- **Member message:** Your claim is partially approved for ₹8000. Items not covered: Teeth Whitening (₹4000) — matches policy exclusion 'Cosmetic or aesthetic procedures'
- **Line items:**
  - Root Canal Treatment (₹8000): covered — listed as covered: 'Root Canal Treatment'
  - Teeth Whitening (₹4000): NOT covered — matches policy exclusion 'Cosmetic or aesthetic procedures'
- **Financial:** claimed ₹12000 → covered ₹8000 → discount ₹0 → co-pay ₹0 → payable ₹8000

**Expectation checks:**

- ✅ decision == PARTIAL — got PARTIAL
- ✅ approved_amount == 8000 — got 8000.0
- ✅ itemizes approved vs rejected lines — verdicts=[('Root Canal Treatment', True), ('Teeth Whitening', False)]
- ✅ line-level rejection reason present — matches policy exclusion 'Cosmetic or aesthetic procedures'

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC006 received: member EMP002, category DENTAL, amount ₹12000, 1 document(s), treatment date 2024-10-15. |
| 2 | extraction | extract_F011 | PASS | F011: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 3 | document_verification | required_documents | PASS | All required documents present for DENTAL: HOSPITAL_BILL. |
| 4 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 5 | document_verification | patient_on_roster | PASS | Patient 'Priya Singh' matches the membership of EMP002. |
| 6 | document_verification | patient_consistency | PASS | All documents belong to the same patient. Patient: Priya Singh. |
| 7 | rules_engine | member_exists | PASS | Member EMP002 (Priya Singh) found on roster. |
| 8 | rules_engine | policy_active | PASS | Treatment date 2024-10-15 within policy period. |
| 9 | rules_engine | minimum_claim_amount | PASS | Claimed ₹12000 ≥ minimum ₹500. |
| 10 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 11 | rules_engine | category_covered | PASS | Category DENTAL is covered (sub-limit ₹10000, co-pay 0%). |
| 12 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 13 | rules_engine | initial_waiting_period | PASS | 197 days since cover start ≥ 30-day initial wait. |
| 14 | rules_engine | condition_waiting_period | PASS | Diagnosis does not map to any condition-specific waiting period. |
| 15 | rules_engine | pre_authorization | PASS | No pre-authorization requirement applies to this category. |
| 16 | rules_engine | line_item_screening | PASS | Root Canal Treatment (₹8000): covered — listed as covered: 'Root Canal Treatment' |
| 17 | rules_engine | line_item_screening | FAIL | Teeth Whitening (₹4000): NOT covered — matches policy exclusion 'Cosmetic or aesthetic procedures' |
| 18 | rules_engine | per_claim_limit | PASS | Payable ₹8000 ≤ per-claim limit ₹10000. |
| 19 | rules_engine | category_sub_limit | PASS | Primary service charges within category sub-limit ₹10000. |
| 20 | rules_engine | annual_opd_limit | PASS | YTD ₹0 + this claim within the annual OPD limit ₹50000. |
| 21 | rules_engine | network_hospital | INFO | Hospital 'Smile Dental Clinic' is NOT in the network list. |
| 22 | rules_engine | financial_computation | PASS | Final payable: ₹8000. |
| 23 | fraud_detection | fraud_signals | PASS | No fraud signals: same-day, monthly, high-value, and document-alteration checks all clear. |
| 24 | finalize | outcome | INFO | Decision: PARTIAL, approved ₹8000, confidence 0.93 (deductions: -0.02: weakest text-match certainty 'keyword'). |

---

## TC007 — MRI Without Pre-Authorization

- **Status:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.95
- **Member message:** A MRI above ₹10000 requires pre-authorization, which was not obtained. To resubmit: request pre-authorization from your insurer (valid 30 days), then submit this claim again quoting the pre-authorization number.
- **Rejection reasons:** PRE_AUTH_MISSING

**Expectation checks:**

- ✅ decision == REJECTED — got REJECTED
- ✅ rejection_reasons include ['PRE_AUTH_MISSING'] — got ['PRE_AUTH_MISSING']
- ✅ explains pre-auth was required and missing — a mri above ₹10000 requires pre-authorization, which was not obtained. to resubmit: request pre-authorization from your insurer (valid 30 days), then submit this claim again quoting the pre-authorization number. a mri above ₹10000 requires pre-author
- ✅ tells the member how to resubmit — a mri above ₹10000 requires pre-authorization, which was not obtained. to resubmit: request pre-authorization from your insurer (valid 30 days), then submit this claim again quoting the pre-authorization number. a mri above ₹10000 requires pre-author

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC007 received: member EMP007, category DIAGNOSTIC, amount ₹15000, 3 document(s), treatment date 2024-11-02. |
| 2 | extraction | extract_F012 | PASS | F012: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F013 | PASS | F013: LAB_REPORT (GOOD, source=fixture, confidence=1) |
| 4 | extraction | extract_F014 | PASS | F014: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 5 | document_verification | required_documents | PASS | All required documents present for DIAGNOSTIC: PRESCRIPTION, LAB_REPORT, HOSPITAL_BILL. |
| 6 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 7 | document_verification | patient_consistency | PASS | All documents belong to the same patient. |
| 8 | rules_engine | member_exists | PASS | Member EMP007 (Suresh Patil) found on roster. |
| 9 | rules_engine | policy_active | PASS | Treatment date 2024-11-02 within policy period. |
| 10 | rules_engine | minimum_claim_amount | PASS | Claimed ₹15000 ≥ minimum ₹500. |
| 11 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 12 | rules_engine | category_covered | PASS | Category DIAGNOSTIC is covered (sub-limit ₹10000, co-pay 0%). |
| 13 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 14 | rules_engine | initial_waiting_period | PASS | 215 days since cover start ≥ 30-day initial wait. |
| 15 | rules_engine | condition_waiting_period | PASS | Diagnosis does not map to any condition-specific waiting period. |
| 16 | rules_engine | pre_authorization | FAIL | 'MRI Lumbar Spine' is a high-value test (MRI) at ₹15000 > ₹10000 threshold, and no pre-authorization was obtained. |
| 17 | rules_engine | per_claim_limit | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 18 | rules_engine | line_item_screening | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 19 | fraud_detection | fraud_signals | PASS | No fraud signals: same-day, monthly, high-value, and document-alteration checks all clear. |
| 20 | finalize | outcome | INFO | Decision: REJECTED, approved ₹0, confidence 0.95 (no deductions). |

---

## TC008 — Per-Claim Limit Exceeded

- **Status:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.95
- **Member message:** The claimed amount ₹7500 exceeds the per-claim limit of ₹5000 under your policy.
- **Rejection reasons:** PER_CLAIM_EXCEEDED
- **Line items:**
  - Consultation Fee (₹2000): covered — no procedure restrictions for this category
  - Medicines (₹5500): covered — no procedure restrictions for this category

**Expectation checks:**

- ✅ decision == REJECTED — got REJECTED
- ✅ rejection_reasons include ['PER_CLAIM_EXCEEDED'] — got ['PER_CLAIM_EXCEEDED']
- ✅ states limit and claimed amount — the claimed amount ₹7500 exceeds the per-claim limit of ₹5000 under your policy. the claimed amount ₹7500 exceeds the per-claim limit of ₹5000 under your policy.

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC008 received: member EMP003, category CONSULTATION, amount ₹7500, 2 document(s), treatment date 2024-10-20. |
| 2 | extraction | extract_F015 | PASS | F015: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F016 | PASS | F016: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for CONSULTATION: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_consistency | PASS | All documents belong to the same patient. |
| 7 | rules_engine | member_exists | PASS | Member EMP003 (Amit Verma) found on roster. |
| 8 | rules_engine | policy_active | PASS | Treatment date 2024-10-20 within policy period. |
| 9 | rules_engine | minimum_claim_amount | PASS | Claimed ₹7500 ≥ minimum ₹500. |
| 10 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 11 | rules_engine | category_covered | PASS | Category CONSULTATION is covered (sub-limit ₹2000, co-pay 10%). |
| 12 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 13 | rules_engine | initial_waiting_period | PASS | 202 days since cover start ≥ 30-day initial wait. |
| 14 | rules_engine | condition_waiting_period | PASS | Diagnosis does not map to any condition-specific waiting period. |
| 15 | rules_engine | pre_authorization | PASS | No pre-authorization requirement applies to this category. |
| 16 | rules_engine | line_item_screening | PASS | Consultation Fee (₹2000): covered — no procedure restrictions for this category |
| 17 | rules_engine | line_item_screening | PASS | Medicines (₹5500): covered — no procedure restrictions for this category |
| 18 | rules_engine | per_claim_limit | FAIL | Payable amount ₹7500 exceeds the per-claim limit ₹5000 (global ₹5000, category sub-limit ₹2000). |
| 19 | fraud_detection | fraud_signals | PASS | No fraud signals: same-day, monthly, high-value, and document-alteration checks all clear. |
| 20 | finalize | outcome | INFO | Decision: REJECTED, approved ₹0, confidence 0.95 (no deductions). |

---

## TC009 — Fraud Signal — Multiple Same-Day Claims

- **Status:** MANUAL_REVIEW
- **Approved amount:** ₹0
- **Confidence:** 0.95
- **Member message:** Your claim needs a quick manual check by our team before payout. No action is needed from you right now.
- **Financial:** claimed ₹4800 → covered ₹4800 → discount ₹0 → co-pay ₹480 → payable ₹4320
- **Fraud signals:** 4 claims from this member on 2024-10-30 (limit 2); prior claims today: CLM_0081 ₹1200, CLM_0082 ₹1800, CLM_0083 ₹2100; providers: City Clinic A, City Clinic B, Wellness Center

**Expectation checks:**

- ✅ decision == MANUAL_REVIEW — got MANUAL_REVIEW
- ✅ flags the same-day pattern — signals=['4 claims from this member on 2024-10-30 (limit 2); prior claims today: CLM_0081 ₹1200, CLM_0082 ₹1800, CLM_0083 ₹2100; providers: City Clinic A, City Clinic B, Wellness Center']
- ✅ routes to manual review, not auto-reject — status=MANUAL_REVIEW
- ✅ specific signals included in output — 1 signal(s)

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC009 received: member EMP008, category CONSULTATION, amount ₹4800, 2 document(s), treatment date 2024-10-30. |
| 2 | extraction | extract_F017 | PASS | F017: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F018 | PASS | F018: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for CONSULTATION: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_consistency | PASS | All documents belong to the same patient. |
| 7 | rules_engine | member_exists | PASS | Member EMP008 (Ravi Menon) found on roster. |
| 8 | rules_engine | policy_active | PASS | Treatment date 2024-10-30 within policy period. |
| 9 | rules_engine | minimum_claim_amount | PASS | Claimed ₹4800 ≥ minimum ₹500. |
| 10 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 11 | rules_engine | category_covered | PASS | Category CONSULTATION is covered (sub-limit ₹2000, co-pay 10%). |
| 12 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 13 | rules_engine | initial_waiting_period | PASS | 212 days since cover start ≥ 30-day initial wait. |
| 14 | rules_engine | condition_waiting_period | PASS | Diagnosis does not map to any condition-specific waiting period. |
| 15 | rules_engine | pre_authorization | PASS | No pre-authorization requirement applies to this category. |
| 16 | rules_engine | line_item_screening | INFO | No itemized bill lines; claim adjudicated at claim level. |
| 17 | rules_engine | per_claim_limit | PASS | Payable ₹4800 ≤ per-claim limit ₹5000. |
| 18 | rules_engine | category_sub_limit | PASS | Primary service charges within category sub-limit ₹2000. |
| 19 | rules_engine | annual_opd_limit | PASS | YTD ₹0 + this claim within the annual OPD limit ₹50000. |
| 20 | rules_engine | network_hospital | INFO | Hospital 'unknown' is NOT in the network list. |
| 21 | rules_engine | financial_computation | PASS | Co-pay (10%) applied on ₹4800 = ₹480 deducted. Final payable: ₹4320. |
| 22 | fraud_detection | fraud_signals | FAIL | Fraud signals detected; routing to manual review: 4 claims from this member on 2024-10-30 (limit 2); prior claims today: CLM_0081 ₹1200, CLM_0082 ₹1800, CLM_0083 ₹2100; providers: City Clinic A, City Clinic B, Wellness Center |
| 23 | finalize | outcome | INFO | Decision: MANUAL_REVIEW, approved ₹0, confidence 0.95 (no deductions). |

---

## TC010 — Network Hospital — Discount Applied

- **Status:** APPROVED
- **Approved amount:** ₹3240
- **Confidence:** 0.95
- **Member message:** Your claim is approved for ₹3240.
- **Line items:**
  - Consultation Fee (₹1500): covered — no procedure restrictions for this category
  - Medicines (₹3000): covered — no procedure restrictions for this category
- **Financial:** claimed ₹4500 → covered ₹4500 → discount ₹900 → co-pay ₹360 → payable ₹3240

**Expectation checks:**

- ✅ decision == APPROVED — got APPROVED
- ✅ approved_amount == 3240 — got 3240.0
- ✅ network discount applied before co-pay — discount=900.0, after=3600.0, copay=360.0
- ✅ breakdown shown in decision output — Network discount (20%) applied first on ₹4500 = ₹3600. | Co-pay (10%) applied on ₹3600 = ₹360 deducted. | Final payable: ₹3240.

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC010 received: member EMP010, category CONSULTATION, amount ₹4500, 2 document(s), treatment date 2024-11-03. |
| 2 | extraction | extract_F019 | PASS | F019: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F020 | PASS | F020: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for CONSULTATION: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_on_roster | PASS | Patient 'Deepak Shah' matches the membership of EMP010. |
| 7 | document_verification | patient_consistency | PASS | All documents belong to the same patient. Patient: Deepak Shah. |
| 8 | rules_engine | member_exists | PASS | Member EMP010 (Deepak Shah) found on roster. |
| 9 | rules_engine | policy_active | PASS | Treatment date 2024-11-03 within policy period. |
| 10 | rules_engine | minimum_claim_amount | PASS | Claimed ₹4500 ≥ minimum ₹500. |
| 11 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 12 | rules_engine | category_covered | PASS | Category CONSULTATION is covered (sub-limit ₹2000, co-pay 10%). |
| 13 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 14 | rules_engine | initial_waiting_period | PASS | 216 days since cover start ≥ 30-day initial wait. |
| 15 | rules_engine | condition_waiting_period | PASS | Diagnosis does not map to any condition-specific waiting period. |
| 16 | rules_engine | pre_authorization | PASS | No pre-authorization requirement applies to this category. |
| 17 | rules_engine | line_item_screening | PASS | Consultation Fee (₹1500): covered — no procedure restrictions for this category |
| 18 | rules_engine | line_item_screening | PASS | Medicines (₹3000): covered — no procedure restrictions for this category |
| 19 | rules_engine | per_claim_limit | PASS | Payable ₹4500 ≤ per-claim limit ₹5000. |
| 20 | rules_engine | category_sub_limit | PASS | Primary service charges within category sub-limit ₹2000. |
| 21 | rules_engine | annual_opd_limit | PASS | YTD ₹8000 + this claim within the annual OPD limit ₹50000. |
| 22 | rules_engine | network_hospital | INFO | Hospital 'Apollo Hospitals' IS in the network list. |
| 23 | rules_engine | financial_computation | PASS | Network discount (20%) applied first on ₹4500 = ₹3600. Co-pay (10%) applied on ₹3600 = ₹360 deducted. Final payable: ₹3240. |
| 24 | fraud_detection | fraud_signals | PASS | No fraud signals: same-day, monthly, high-value, and document-alteration checks all clear. |
| 25 | finalize | outcome | INFO | Decision: APPROVED, approved ₹3240, confidence 0.95 (no deductions). |

---

## TC011 — Component Failure — Graceful Degradation

- **Status:** APPROVED
- **Approved amount:** ₹4000
- **Confidence:** 0.75
- **Member message:** Your claim is approved for ₹4000.
- **Line items:**
  - Panchakarma Therapy (5 sessions) (₹3000): covered — no procedure restrictions for this category
  - Consultation (₹1000): covered — no procedure restrictions for this category
- **Financial:** claimed ₹4000 → covered ₹4000 → discount ₹0 → co-pay ₹0 → payable ₹4000
- **Component failures:** fraud_detection (Simulated component failure (fraud detection) — injected by the simulate_component_failure flag.)

**Expectation checks:**

- ✅ decision == APPROVED — got APPROVED
- ✅ did not crash / no 500 — pipeline completed
- ✅ failure visible in output — failures=['fraud_detection']
- ✅ confidence below clean-run level (0.95) — got 0.75
- ✅ manual review recommended — True

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC011 received: member EMP006, category ALTERNATIVE_MEDICINE, amount ₹4000, 2 document(s), treatment date 2024-10-28. |
| 2 | extraction | extract_F021 | PASS | F021: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F022 | PASS | F022: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for ALTERNATIVE_MEDICINE: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_consistency | PASS | All documents belong to the same patient. |
| 7 | rules_engine | member_exists | PASS | Member EMP006 (Kavita Nair) found on roster. |
| 8 | rules_engine | policy_active | PASS | Treatment date 2024-10-28 within policy period. |
| 9 | rules_engine | minimum_claim_amount | PASS | Claimed ₹4000 ≥ minimum ₹500. |
| 10 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 11 | rules_engine | category_covered | PASS | Category ALTERNATIVE_MEDICINE is covered (sub-limit ₹8000, co-pay 0%). |
| 12 | rules_engine | registered_practitioner | PASS | Practitioner registration AYUR/KL/2345/2019 present. |
| 13 | rules_engine | exclusions | PASS | No policy exclusion matched the diagnosis, treatment, or billed items. |
| 14 | rules_engine | initial_waiting_period | PASS | 210 days since cover start ≥ 30-day initial wait. |
| 15 | rules_engine | condition_waiting_period | PASS | Diagnosis does not map to any condition-specific waiting period. |
| 16 | rules_engine | pre_authorization | PASS | No pre-authorization requirement applies to this category. |
| 17 | rules_engine | line_item_screening | PASS | Panchakarma Therapy (5 sessions) (₹3000): covered — no procedure restrictions for this category |
| 18 | rules_engine | line_item_screening | PASS | Consultation (₹1000): covered — no procedure restrictions for this category |
| 19 | rules_engine | per_claim_limit | PASS | Payable ₹4000 ≤ per-claim limit ₹8000. |
| 20 | rules_engine | category_sub_limit | PASS | Primary service charges within category sub-limit ₹8000. |
| 21 | rules_engine | annual_opd_limit | PASS | YTD ₹0 + this claim within the annual OPD limit ₹50000. |
| 22 | rules_engine | network_hospital | INFO | Hospital 'Ayur Wellness Centre' is NOT in the network list. |
| 23 | rules_engine | financial_computation | PASS | Final payable: ₹4000. |
| 24 | fraud_detection | component_health | ERROR | fraud_detection failed and was skipped: Simulated component failure (fraud detection) — injected by the simulate_component_failure flag.. Impact: fraud screening skipped for this claim |
| 25 | finalize | outcome | INFO | Decision: APPROVED, approved ₹4000, confidence 0.75 (deductions: -0.2: 1 pipeline component(s) failed and were skipped). Degraded run — manual review recommended. |

---

## TC012 — Excluded Treatment

- **Status:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.93
- **Member message:** 'Morbid Obesity — BMI 37' falls under the policy exclusion 'Obesity and weight loss programs' and is not covered.
- **Rejection reasons:** EXCLUDED_CONDITION

**Expectation checks:**

- ✅ decision == REJECTED — got REJECTED
- ✅ rejection_reasons include ['EXCLUDED_CONDITION'] — got ['EXCLUDED_CONDITION']
- ✅ confidence above 0.90 — got 0.93

**Full trace:**

| # | Component | Check | Status | Detail |
|---|-----------|-------|--------|--------|
| 1 | intake | claim_received | INFO | Claim TC012 received: member EMP009, category CONSULTATION, amount ₹8000, 2 document(s), treatment date 2024-10-18. |
| 2 | extraction | extract_F023 | PASS | F023: PRESCRIPTION (GOOD, source=fixture, confidence=1) |
| 3 | extraction | extract_F024 | PASS | F024: HOSPITAL_BILL (GOOD, source=fixture, confidence=1) |
| 4 | document_verification | required_documents | PASS | All required documents present for CONSULTATION: PRESCRIPTION, HOSPITAL_BILL. |
| 5 | document_verification | document_readability | PASS | All documents are readable and their material fields were extracted with usable confidence. |
| 6 | document_verification | patient_consistency | PASS | All documents belong to the same patient. |
| 7 | rules_engine | member_exists | PASS | Member EMP009 (Anita Desai) found on roster. |
| 8 | rules_engine | policy_active | PASS | Treatment date 2024-10-18 within policy period. |
| 9 | rules_engine | minimum_claim_amount | PASS | Claimed ₹8000 ≥ minimum ₹500. |
| 10 | rules_engine | submission_deadline | PASS | Submitted 0 days after treatment (limit 30). |
| 11 | rules_engine | category_covered | PASS | Category CONSULTATION is covered (sub-limit ₹2000, co-pay 10%). |
| 12 | rules_engine | exclusions | FAIL | 'Morbid Obesity — BMI 37' matches policy exclusion 'Obesity and weight loss programs'. |
| 13 | rules_engine | waiting_periods | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 14 | rules_engine | pre_authorization | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 15 | rules_engine | per_claim_limit | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 16 | rules_engine | line_item_screening | SKIPPED | Skipped: claim already terminally rejected by an earlier check. |
| 17 | fraud_detection | fraud_signals | PASS | No fraud signals: same-day, monthly, high-value, and document-alteration checks all clear. |
| 18 | finalize | outcome | INFO | Decision: REJECTED, approved ₹0, confidence 0.93 (deductions: -0.02: weakest text-match certainty 'keyword'). |
