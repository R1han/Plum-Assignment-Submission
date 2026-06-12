export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface TraceStep {
  component: string;
  check: string;
  status: "PASS" | "FAIL" | "SKIPPED" | "ERROR" | "INFO";
  detail: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface DocumentIssue {
  code: string;
  message: string;
  file_id?: string | null;
  expected?: string | null;
  found?: string | null;
}

export interface LineItemVerdict {
  description: string;
  amount: number;
  covered: boolean;
  reason: string;
}

export interface FinancialBreakdown {
  claimed_amount: number;
  covered_amount: number;
  network_discount_percent: number;
  network_discount_amount: number;
  amount_after_discount: number;
  copay_percent: number;
  copay_amount: number;
  payable_amount: number;
  notes: string[];
}

export interface Decision {
  status: "APPROVED" | "PARTIAL" | "REJECTED" | "MANUAL_REVIEW";
  approved_amount: number;
  reasons: string[];
  rejection_reasons: string[];
  line_items: LineItemVerdict[];
  financial: FinancialBreakdown | null;
  confidence_score: number;
  member_message: string;
  fraud_signals: string[];
  manual_review_recommended: boolean;
}

export interface ComponentFailure {
  component: string;
  error: string;
  impact: string;
}

export interface ClaimOutcome {
  claim_id: string;
  outcome_type: "DECISION" | "DOCUMENT_ISSUE";
  decision: Decision | null;
  document_issues: DocumentIssue[];
  degraded: boolean;
  component_failures: ComponentFailure[];
  trace: TraceStep[];
}

export interface ClaimListItem {
  claim_id: string;
  member_id: string;
  claim_category: string;
  treatment_date: string;
  claimed_amount: number;
  outcome_type: string;
  status: string | null;
  approved_amount: number;
  confidence_score: number | null;
  degraded: boolean;
  created_at: string;
}

export interface PolicySummary {
  policy_id: string;
  policy_name: string;
  insurer: string;
  categories: string[];
  document_requirements: Record<string, { required: string[]; optional: string[] }>;
  members: { member_id: string; name: string; relationship: string }[];
  network_hospitals: string[];
  per_claim_limit: number;
}

async function check(res: Response) {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body.slice(0, 300)}`);
  }
  return res;
}

export async function getPolicy(): Promise<PolicySummary> {
  return (await check(await fetch(`${API_BASE}/api/policy`))).json();
}

export async function listClaims(): Promise<ClaimListItem[]> {
  return (
    await check(await fetch(`${API_BASE}/api/claims`, { cache: "no-store" }))
  ).json();
}

export async function getClaim(
  id: string
): Promise<{ claim_id: string; submission: unknown; outcome: ClaimOutcome }> {
  return (
    await check(
      await fetch(`${API_BASE}/api/claims/${id}`, { cache: "no-store" })
    )
  ).json();
}

export async function submitClaimJson(payload: unknown): Promise<ClaimOutcome> {
  return (
    await check(
      await fetch(`${API_BASE}/api/claims`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    )
  ).json();
}

export async function submitClaimUpload(form: FormData): Promise<ClaimOutcome> {
  return (
    await check(
      await fetch(`${API_BASE}/api/claims/upload`, {
        method: "POST",
        body: form,
      })
    )
  ).json();
}
