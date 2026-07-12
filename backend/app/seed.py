"""Idempotent seed: a first admin + a demoable 'Auto Accident' questionnaire.

Run with:  python -m app.seed
"""
import asyncio

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import (
    AdminUser,
    InjuryType,
    Question,
    QuestionOption,
    QuestionType,
    SummaryTemplate,
)
from app.security import hash_password
from app.services.estimate_pipeline.jurisdiction_data import seed_jurisdiction_defaults

# Each tuple: (slug, type, prompt, help_text, is_required, page_group, config, options)
# options is a list of (label, value).
_QUESTIONS = [
    (
        "role",
        QuestionType.single_choice,
        "Were you the driver, a passenger, or a pedestrian?",
        None,
        True,
        None,
        {},
        [("Driver", "driver"), ("Passenger", "passenger"), ("Pedestrian", "pedestrian")],
    ),
    ("accident_date", QuestionType.date, "When did the accident occur?", None, True, None, {}, []),
    (
        "location",
        QuestionType.single_choice,
        "Where did the accident happen?",
        None,
        True,
        None,
        {},
        [
            ("Highway / freeway", "highway"),
            ("City street", "city_street"),
            ("Intersection", "intersection"),
            ("Parking lot", "parking_lot"),
            ("Other", "other"),
        ],
    ),
    (
        "police_report",
        QuestionType.yes_no,
        "Did the police come to the scene?",
        "A police report can strengthen your case.",
        True,
        1,
        {},
        [],
    ),
    (
        "sought_care",
        QuestionType.yes_no,
        "Did you go to the emergency room or see a doctor?",
        None,
        True,
        1,
        {},
        [],
    ),
    (
        "injured_areas",
        QuestionType.multi_choice,
        "Which parts of your body were injured?",
        "Select all that apply.",
        True,
        None,
        {},
        [
            ("Neck", "neck"),
            ("Back", "back"),
            ("Head", "head"),
            ("Shoulders", "shoulders"),
            ("Knees", "knees"),
            ("Other", "other"),
        ],
    ),
    (
        "pain_level",
        QuestionType.single_choice,
        "How would you describe your pain?",
        None,
        True,
        None,
        {},
        [("Mild", "mild"), ("Moderate", "moderate"), ("Severe", "severe")],
    ),
    (
        "missed_work_days",
        QuestionType.number,
        "Approximately how many days of work have you missed?",
        None,
        False,
        None,
        {"min": 0, "placeholder": "e.g. 5"},
        [],
    ),
    (
        "returned_to_work",
        QuestionType.yes_no,
        "Have you been able to return to work?",
        None,
        False,
        None,
        {},
        [],
    ),
    (
        "insurer",
        QuestionType.short_text,
        "What insurance company is involved (if known)?",
        None,
        False,
        None,
        {"placeholder": "e.g. State Farm"},
        [],
    ),
    (
        "description",
        QuestionType.long_text,
        "In your own words, describe what happened.",
        "Include anything you think is important.",
        True,
        None,
        {"placeholder": "Tell us the story of your accident…"},
        [],
    ),
]

_SUMMARY_BODY = """Thank you for sharing the details of your auto accident.

Here's a summary of what you told us:

- Your role in the accident: {{role}}
- Date of accident: {{accident_date}}
- Where it happened: {{location}}
- Police came to the scene: {{police_report}}
- Sought medical care: {{sought_care}}
- Injured areas: {{injured_areas}}
- Pain level: {{pain_level}}
- Days of work missed: {{missed_work_days}}
- Insurance company: {{insurer}}

What you described:
{{description}}

Based on cases like yours, patients in similar situations often recover settlements in the range below. This is an early, transparent estimate — not a promise."""


async def _seed_admin(db) -> None:
    existing = await db.scalar(select(AdminUser).where(AdminUser.email == settings.admin_email))
    if existing is None:
        db.add(
            AdminUser(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
            )
        )
        print(f"Created admin {settings.admin_email}")
    else:
        print(f"Admin {settings.admin_email} already exists; skipping")


async def _seed_auto_accident(db) -> None:
    existing = await db.scalar(select(InjuryType).where(InjuryType.slug == "auto-accident"))
    if existing is not None:
        print("Injury type 'auto-accident' already exists; skipping")
        return

    injury = InjuryType(
        slug="auto-accident",
        name="Auto Accident",
        description="You were involved in a car, truck, or motorcycle accident.",
        display_order=0,
        is_published=True,
    )
    for order, (slug, qtype, prompt, help_text, required, group, config, options) in enumerate(
        _QUESTIONS
    ):
        injury.questions.append(
            Question(
                slug=slug,
                type=qtype,
                prompt=prompt,
                help_text=help_text,
                is_required=required,
                display_order=order,
                page_group=group,
                config=config,
                options=[
                    QuestionOption(label=label, value=value, display_order=i)
                    for i, (label, value) in enumerate(options)
                ],
            )
        )
    injury.summary_template = SummaryTemplate(
        body=_SUMMARY_BODY, estimate_min=5000, estimate_max=25000
    )
    db.add(injury)
    print("Created 'Auto Accident' injury type with seeded questionnaire")


async def main() -> None:
    async with SessionLocal() as db:
        await _seed_admin(db)
        await _seed_auto_accident(db)
        inserted = await seed_jurisdiction_defaults(db)
        print(f"Jurisdiction rules: inserted {inserted} missing state rows")
        await db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
