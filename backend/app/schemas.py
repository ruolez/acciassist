import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import CaseStage, CaseUpdateKind, EmailStatus, IntakeStatus, QuestionType


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


# ── Questions ──────────────────────────────────────────────────────────
class QuestionOptionIn(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=255)


class QuestionOptionOut(ORMModel):
    id: int
    label: str
    value: str
    display_order: int


class QuestionIn(BaseModel):
    type: QuestionType
    prompt: str = Field(min_length=1)
    help_text: str | None = None
    is_required: bool = True
    page_group: int | None = None
    config: dict = Field(default_factory=dict)
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


class IntakeSessionDetailOut(IntakeSessionOut):
    answers: list[AnswerOut]


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


class TestEmailIn(BaseModel):
    to_email: EmailStr


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
