"""Typed view of policy_terms.json. No policy values are hardcoded anywhere
else in the system — everything flows from this file."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class PolicyHolder(BaseModel):
    company_name: str
    employee_count: int
    policy_start_date: date
    policy_end_date: date
    renewal_status: str


class FamilyFloater(BaseModel):
    enabled: bool
    combined_limit: float
    covered_relationships: list[str]


class Coverage(BaseModel):
    sum_insured_per_employee: float
    annual_opd_limit: float
    per_claim_limit: float
    family_floater: FamilyFloater


class OpdCategory(BaseModel):
    sub_limit: float
    copay_percent: float = 0.0
    network_discount_percent: float = 0.0
    requires_prescription: bool = False
    requires_pre_auth: bool = False
    pre_auth_threshold: float | None = None
    high_value_tests_requiring_pre_auth: list[str] = Field(default_factory=list)
    branded_drug_copay_percent: float | None = None
    generic_mandatory: bool = False
    requires_dental_report: bool = False
    requires_registered_practitioner: bool = False
    max_sessions_per_year: int | None = None
    covered: bool = True
    covered_procedures: list[str] = Field(default_factory=list)
    excluded_procedures: list[str] = Field(default_factory=list)
    covered_items: list[str] = Field(default_factory=list)
    excluded_items: list[str] = Field(default_factory=list)
    covered_systems: list[str] = Field(default_factory=list)


class WaitingPeriods(BaseModel):
    initial_waiting_period_days: int
    pre_existing_conditions_days: int
    specific_conditions: dict[str, int]


class Exclusions(BaseModel):
    conditions: list[str]
    dental_exclusions: list[str] = Field(default_factory=list)
    vision_exclusions: list[str] = Field(default_factory=list)


class PreAuthorization(BaseModel):
    required_for: list[str]
    validity_days: int


class SubmissionRules(BaseModel):
    deadline_days_from_treatment: int
    minimum_claim_amount: float
    currency: str = "INR"


class DocumentRequirement(BaseModel):
    required: list[str]
    optional: list[str] = Field(default_factory=list)


class FraudThresholds(BaseModel):
    same_day_claims_limit: int
    monthly_claims_limit: int
    high_value_claim_threshold: float
    auto_manual_review_above: float
    fraud_score_manual_review_threshold: float


class Member(BaseModel):
    member_id: str
    name: str
    date_of_birth: date
    gender: str
    relationship: str
    join_date: date | None = None
    dependents: list[str] = Field(default_factory=list)
    primary_member_id: str | None = None


class Policy(BaseModel):
    policy_id: str
    policy_name: str
    insurer: str
    policy_holder: PolicyHolder
    coverage: Coverage
    opd_categories: dict[str, OpdCategory]
    waiting_periods: WaitingPeriods
    exclusions: Exclusions
    pre_authorization: PreAuthorization
    network_hospitals: list[str]
    submission_rules: SubmissionRules
    document_requirements: dict[str, DocumentRequirement]
    fraud_thresholds: FraudThresholds
    members: list[Member]

    def get_member(self, member_id: str) -> Member | None:
        return next((m for m in self.members if m.member_id == member_id), None)

    def get_category(self, category: str) -> OpdCategory | None:
        return self.opd_categories.get(category.lower())

    def get_document_requirement(self, category: str) -> DocumentRequirement | None:
        return self.document_requirements.get(category.upper())

    def member_join_date(self, member_id: str) -> date | None:
        """Join date for a member; dependents inherit their primary member's."""
        member = self.get_member(member_id)
        if member is None:
            return None
        if member.join_date is not None:
            return member.join_date
        if member.primary_member_id:
            primary = self.get_member(member.primary_member_id)
            if primary:
                return primary.join_date
        return None

    def is_network_hospital(self, hospital_name: str | None) -> bool:
        if not hospital_name:
            return False
        needle = hospital_name.strip().lower()
        return any(
            h.lower() in needle or needle in h.lower()
            for h in self.network_hospitals
        )
