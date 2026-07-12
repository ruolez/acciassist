import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    CaseStage,
    CaseUpdateKind,
    EmailStatus,
    EstimateStatus,
    IntakeStatus,
    QuestionType,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth / admins ──────────────────────────────────────────────────────
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AdminOut(ORMModel):
    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime


class AdminCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


# ── Injury types ───────────────────────────────────────────────────────
class InjuryTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_published: bool = False


class InjuryTypeOut(ORMModel):
    id: int
    slug: str
    name: str
    description: str | None
    display_order: int
    is_published: bool


class ReorderIn(BaseModel):
    ordered_ids: list[int]


class QuestionLayoutIn(BaseModel):
    """Wizard page structure: each inner list is one page, in order."""

    pages: list[list[int]]

    @field_validator("pages")
    @classmethod
    def _no_empty_pages_or_duplicates(cls, pages: list[list[int]]) -> list[list[int]]:
        flat = [qid for page in pages for qid in page]
        if any(not page for page in pages):
            raise ValueError("pages must not be empty")
        if len(flat) != len(set(flat)):
            raise ValueError("a question can only appear on one page")
        return pages


# ── Questions ──────────────────────────────────────────────────────────
class QuestionOptionIn(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=255)


class QuestionOptionOut(ORMModel):
    id: int
    label: str
    value: str
    display_order: int


class QuestionConfigIn(BaseModel):
    """Typed per-question settings stored in the config JSONB column. Unknown
    keys from older clients are dropped on write; existing rows keep whatever
    they have until re-saved."""

    model_config = ConfigDict(extra="ignore")

    placeholder: str | None = Field(default=None, max_length=255)
    min: float | None = None
    max: float | None = None
    max_length: int | None = Field(default=None, ge=1, le=10_000)
    disallow_future: bool | None = None

    @model_validator(mode="after")
    def _min_not_above_max(self) -> "QuestionConfigIn":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must not be greater than max")
        return self


class QuestionIn(BaseModel):
    type: QuestionType
    prompt: str = Field(min_length=1)
    help_text: str | None = None
    is_required: bool = True
    config: QuestionConfigIn = Field(default_factory=QuestionConfigIn)
    options: list[QuestionOptionIn] = Field(default_factory=list)


class QuestionOut(ORMModel):
    id: int
    slug: str
    type: QuestionType
    prompt: str
    help_text: str | None
    is_required: bool
    display_order: int
    page_group: int | None
    config: dict
    options: list[QuestionOptionOut]


# ── Summary template ───────────────────────────────────────────────────
class SummaryTemplateIn(BaseModel):
    body: str = ""
    estimate_min: int | None = None
    estimate_max: int | None = None
    estimate_note: str = "Upon closer inspection our experts will provide a better estimate."


class SummaryTemplateOut(ORMModel):
    id: int
    body: str
    estimate_min: int | None
    estimate_max: int | None
    estimate_note: str


# ── Public intake ──────────────────────────────────────────────────────
class IntakeStartIn(BaseModel):
    injury_type_id: int


class IntakePage(BaseModel):
    """One screen of the wizard: one or more questions shown together."""

    page_index: int
    questions: list[QuestionOut]


class IntakeStartOut(BaseModel):
    session_id: uuid.UUID
    injury_type: InjuryTypeOut
    pages: list[IntakePage]
    total_pages: int


class AnswerIn(BaseModel):
    question_id: int
    value: bool | int | float | str | list[str] | None

    @field_validator("value")
    @classmethod
    def _cap_value_size(
        cls, v: bool | int | float | str | list[str] | None
    ) -> bool | int | float | str | list[str] | None:
        if isinstance(v, str) and len(v) > 10_000:
            raise ValueError("answer text is too long")
        if isinstance(v, list):
            if len(v) > 50:
                raise ValueError("too many selected options")
            if any(len(item) > 255 for item in v):
                raise ValueError("selected option value is too long")
        return v


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(max_length=100)


class SummaryOut(BaseModel):
    body: str
    estimate_min: int | None
    estimate_max: int | None
    estimate_note: str


class PublicWarning(BaseModel):
    code: str
    severity: str
    message: str
    deadline: date | None = None


class PublicGate(BaseModel):
    code: str
    title: str
    explanation: str


class PublicEstimateOut(BaseModel):
    """Patient-facing estimate. Built from an allowlist of the assembled
    result: pipeline internals (extraction, samples, comps, adversarial raw
    output, stage errors, model names) are never exposed here."""

    status: Literal["none", "pending", "completed", "failed"]
    # Gross settlement range (kept as payout_* for compatibility).
    payout_min: int | None = None
    payout_max: int | None = None
    # Estimated in-pocket range after fee, case costs, and lien assumptions.
    net_min: int | None = None
    net_max: int | None = None
    fee_pct_assumed: float | None = None
    drivers: list[str] | None = None
    reducers: list[str] | None = None
    improvements: list[str] | None = None
    warnings: list[PublicWarning] | None = None
    gated: PublicGate | None = None
    disclaimer: str | None = None


# ── Leads ──────────────────────────────────────────────────────────────
class LeadIn(BaseModel):
    intake_session_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)


class LeadOut(ORMModel):
    id: int
    intake_session_id: uuid.UUID | None
    name: str
    email: EmailStr
    phone: str | None
    created_at: datetime


# ── Admin: submissions ─────────────────────────────────────────────────
class AnswerOut(ORMModel):
    question_id: int
    value: object


class IntakeSessionOut(ORMModel):
    id: uuid.UUID
    injury_type_id: int
    status: IntakeStatus
    started_at: datetime
    completed_at: datetime | None


class CaseEstimateAdminOut(ORMModel):
    status: EstimateStatus
    payout_min: int | None
    payout_max: int | None
    case_cost_min: int | None
    case_cost_max: int | None
    gross_min: int | None = None
    gross_max: int | None = None
    net_min: int | None = None
    net_max: int | None = None
    confidence: str | None
    reasoning: str | None
    missing_info: list[str] | None
    result: dict | None = None
    internals: dict | None = None
    stage_status: dict | None = None
    model: str | None
    error: str | None
    updated_at: datetime


class IntakeSessionDetailOut(IntakeSessionOut):
    answers: list[AnswerOut]
    estimate: CaseEstimateAdminOut | None = None


# ── Admin: jurisdiction rules ──────────────────────────────────────────
class JurisdictionRuleOut(ORMModel):
    state_code: str
    state_name: str
    comparative_rule: Literal["pure", "modified_50", "modified_51", "contributory"]
    no_fault: bool
    pip_threshold_note: str | None
    sol_years_pi: float
    sol_note: str | None
    noneconomic_cap: int | None
    cap_note: str | None
    collateral_source_note: str | None
    needs_review: bool
    updated_at: datetime


class JurisdictionRuleIn(BaseModel):
    comparative_rule: Literal["pure", "modified_50", "modified_51", "contributory"]
    no_fault: bool = False
    pip_threshold_note: str | None = Field(default=None, max_length=2000)
    sol_years_pi: float = Field(gt=0, le=20)
    sol_note: str | None = Field(default=None, max_length=2000)
    noneconomic_cap: int | None = Field(default=None, ge=0)
    cap_note: str | None = Field(default=None, max_length=2000)
    collateral_source_note: str | None = Field(default=None, max_length=2000)
    needs_review: bool = True


# ── Admin: settings ────────────────────────────────────────────────────
class SettingsOut(ORMModel):
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password_set: bool
    smtp_tls_mode: Literal["none", "starttls", "ssl"]
    from_email: str | None
    from_name: str
    app_base_url: str | None
    openrouter_api_key_set: bool
    openrouter_model: str | None
    comps_enabled: bool
    comps_model: str | None
    sample_count: int
    contingency_fee_pct: float


class SettingsIn(BaseModel):
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=255)
    # None/omitted keeps the stored password; "" clears it.
    smtp_password: str | None = Field(default=None, max_length=255)
    smtp_tls_mode: Literal["none", "starttls", "ssl"] = "starttls"
    from_email: EmailStr | None = None
    from_name: str = Field(default="AcciAssist", min_length=1, max_length=200)
    app_base_url: str | None = Field(default=None, max_length=255)
    # None/omitted keeps the stored key; "" clears it.
    openrouter_api_key: str | None = Field(default=None, max_length=255)
    openrouter_model: str | None = Field(default=None, max_length=255)
    comps_enabled: bool = False
    comps_model: str | None = Field(default=None, max_length=255)
    sample_count: int = Field(default=5, ge=1, le=9)
    contingency_fee_pct: float = Field(default=33.3, ge=10, le=50)


class TestEmailIn(BaseModel):
    to_email: EmailStr


class OpenRouterModelOut(BaseModel):
    id: str
    name: str
    context_length: int | None
    prompt_price: str | None
    completion_price: str | None
    supports_structured_outputs: bool


class QuestionPayloadOut(BaseModel):
    """A stored proposal payload — mirrors QuestionIn for output."""

    type: QuestionType
    prompt: str
    help_text: str | None = None
    is_required: bool = True
    config: dict = Field(default_factory=dict)
    options: list[QuestionOptionIn] = Field(default_factory=list)


class ProposalAddOut(BaseModel):
    id: str
    kind: Literal["add"]
    payload: QuestionPayloadOut
    rationale: str
    applied: bool = False
    applied_at: datetime | None = None
    created_question_id: int | None = None


class ProposalEditOut(BaseModel):
    id: str
    kind: Literal["edit"]
    question_id: int
    payload: QuestionPayloadOut
    rationale: str
    change_summary: str
    applied: bool = False
    applied_at: datetime | None = None


ProposalOut = Annotated[ProposalAddOut | ProposalEditOut, Field(discriminator="kind")]


class AdviceApplyIn(BaseModel):
    proposal_ids: list[str] = Field(min_length=1, max_length=50)


class EstimateAdviceOut(ORMModel):
    content: str
    proposals: list[ProposalOut] | None = None
    model: str | None
    updated_at: datetime


class EmailLogOut(ORMModel):
    id: int
    to_email: str
    subject: str
    purpose: str
    status: EmailStatus
    error: str | None
    case_id: int | None
    created_at: datetime


# ── User auth ──────────────────────────────────────────────────────────
class UserOut(ORMModel):
    id: int
    email: EmailStr
    name: str
    phone: str | None
    created_at: datetime


class ClaimVerifyIn(BaseModel):
    token: str = Field(min_length=1, max_length=255)


class ClaimVerifyOut(BaseModel):
    email: EmailStr
    name: str


class ClaimIn(BaseModel):
    token: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)


class ResendClaimIn(BaseModel):
    email: EmailStr


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)


# ── Cases ──────────────────────────────────────────────────────────────
class CaseUpdateOut(ORMModel):
    id: int
    kind: CaseUpdateKind
    body: str
    created_at: datetime


class CaseListOut(BaseModel):
    id: int
    stage: CaseStage
    created_at: datetime
    injury_type_name: str | None
    estimate_min: int | None
    estimate_max: int | None


class CaseDetailOut(CaseListOut):
    updates: list[CaseUpdateOut]
    summary: SummaryOut | None
    name: str
    email: EmailStr
    phone: str | None


class CaseStageIn(BaseModel):
    stage: CaseStage


class CaseUpdateIn(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class AdminCaseListOut(BaseModel):
    id: int
    stage: CaseStage
    created_at: datetime
    lead_name: str
    lead_email: EmailStr
    lead_phone: str | None
    user_claimed: bool
    injury_type_name: str | None


class AdminCaseUpdateOut(CaseUpdateOut):
    admin_email: EmailStr | None


class AdminCaseDetailOut(AdminCaseListOut):
    intake_session_id: uuid.UUID | None
    updates: list[AdminCaseUpdateOut]
    estimate: CaseEstimateAdminOut | None = None
