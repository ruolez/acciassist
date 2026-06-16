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
