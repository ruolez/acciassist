import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import IntakeStatus, QuestionType


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
    value: object


class AnswersIn(BaseModel):
    answers: list[AnswerIn]


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
