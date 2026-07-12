import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class QuestionType(str, enum.Enum):
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    short_text = "short_text"
    number = "number"
    date = "date"
    yes_no = "yes_no"
    long_text = "long_text"


class IntakeStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"


class CaseStage(str, enum.Enum):
    new = "new"
    under_review = "under_review"
    documents_needed = "documents_needed"
    negotiating = "negotiating"
    settled = "settled"
    closed = "closed"


STAGE_LABELS: dict[CaseStage, str] = {
    CaseStage.new: "New",
    CaseStage.under_review: "Under review",
    CaseStage.documents_needed: "Documents needed",
    CaseStage.negotiating: "Negotiating",
    CaseStage.settled: "Settled",
    CaseStage.closed: "Closed",
}


class TokenPurpose(str, enum.Enum):
    account_claim = "account_claim"
    password_reset = "password_reset"


class CaseUpdateKind(str, enum.Enum):
    message = "message"
    stage_change = "stage_change"


class EmailStatus(str, enum.Enum):
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class EstimateStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InjuryType(Base):
    __tablename__ = "injury_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    questions: Mapped[list["Question"]] = relationship(
        back_populates="injury_type",
        cascade="all, delete-orphan",
        order_by="Question.display_order",
    )
    summary_template: Mapped["SummaryTemplate | None"] = relationship(
        back_populates="injury_type", cascade="all, delete-orphan", uselist=False
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    injury_type_id: Mapped[int] = mapped_column(
        ForeignKey("injury_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    injury_type: Mapped["InjuryType"] = relationship(back_populates="questions")
    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionOption.display_order",
    )

    __table_args__ = (UniqueConstraint("injury_type_id", "slug", name="uq_question_slug"),)


class QuestionOption(Base):
    __tablename__ = "question_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    question: Mapped["Question"] = relationship(back_populates="options")


class SummaryTemplate(Base):
    __tablename__ = "summary_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    injury_type_id: Mapped[int] = mapped_column(
        ForeignKey("injury_types.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estimate_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimate_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimate_note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="Upon closer inspection our experts will provide a better estimate.",
    )

    injury_type: Mapped["InjuryType"] = relationship(back_populates="summary_template")


class IntakeSession(Base):
    __tablename__ = "intake_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    injury_type_id: Mapped[int] = mapped_column(
        ForeignKey("injury_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[IntakeStatus] = mapped_column(
        Enum(IntakeStatus, name="intake_status"),
        nullable=False,
        default=IntakeStatus.in_progress,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    answers: Mapped[list["IntakeAnswer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class CaseEstimate(Base):
    """AI-generated estimate for one intake session; a re-run overwrites the
    row in place. No row at all means AI was not configured at completion."""

    __tablename__ = "case_estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intake_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intake_sessions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[EstimateStatus] = mapped_column(
        Enum(EstimateStatus, name="estimate_status"),
        nullable=False,
        default=EstimateStatus.pending,
    )
    payout_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payout_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    case_cost_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    case_cost_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_info: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EstimateAdvice(Base):
    """AI recommendations on what a questionnaire should ask to allow accurate
    estimates; one row per injury type, overwritten on regenerate."""

    __tablename__ = "estimate_advice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    injury_type_id: Mapped[int] = mapped_column(
        ForeignKey("injury_types.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IntakeAnswer(Base):
    __tablename__ = "intake_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("intake_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    # JSONB stores any answer shape directly: scalar (text/number/bool), or a
    # list of option values for multi-choice questions.
    value: Mapped[object] = mapped_column(JSONB, nullable=False)

    session: Mapped["IntakeSession"] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_answer_session_question"),
    )


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intake_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("intake_sessions.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    intake_session: Mapped["IntakeSession | None"] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # NULL until the user claims their account by setting a password.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cases: Mapped[list["Case"]] = relationship(
        back_populates="user", order_by="Case.created_at.desc()"
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 hex of the raw token; the raw value only ever appears in the
    # emailed link, so a DB dump cannot be replayed.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[TokenPurpose] = mapped_column(
        Enum(TokenPurpose, name="token_purpose"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stage: Mapped[CaseStage] = mapped_column(
        Enum(CaseStage, name="case_stage"), nullable=False, default=CaseStage.new
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="cases")
    lead: Mapped["Lead"] = relationship()
    updates: Mapped[list["CaseUpdate"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="CaseUpdate.created_at",
    )


class CaseUpdate(Base):
    __tablename__ = "case_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[CaseUpdateKind] = mapped_column(
        Enum(CaseUpdateKind, name="case_update_kind"),
        nullable=False,
        default=CaseUpdateKind.message,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped["Case"] = relationship(back_populates="updates")
    admin: Mapped["AdminUser | None"] = relationship()


class AppSettings(Base):
    """Single-row (id=1) admin-editable settings; lazily created on first read."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_tls_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="starttls")
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str] = mapped_column(String(200), nullable=False, default="AcciAssist")
    # Public origin used to build links in emails, e.g. "https://acciassist.com".
    app_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    openrouter_api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    openrouter_model: Mapped[str | None] = mapped_column(String(255), nullable=True)


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[EmailStatus] = mapped_column(
        Enum(EmailStatus, name="email_status"), nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
