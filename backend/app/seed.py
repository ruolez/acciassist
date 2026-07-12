"""Idempotent seed: a first admin, high-signal 'Auto Accident' and
'Slip & Fall' questionnaires, and the 51-state jurisdiction baseline.

Run with:  python -m app.seed

Question slugs are the stable contract the estimate pipeline's extraction
stage keys on (they are passed as [slug] hints in the prompt) — keep them
snake_case and stable. Every dollar question has a paired "...documented"
yes/no: self-reported and provable amounts are weighted very differently.
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
from app.services.estimate_pipeline.jurisdiction_data import (
    JURISDICTION_DEFAULTS,
    seed_jurisdiction_defaults,
)

_STATE_OPTIONS = [(row["state_name"], row["state_code"]) for row in JURISDICTION_DEFAULTS]

# Shared blocks (same slugs across injury types so extraction stays uniform).
# Each tuple: (slug, type, prompt, help_text, is_required, page_group, config, options)
# options is a list of (label, value).


def _where_and_when(group_base: int) -> list[tuple]:
    return [
        (
            "state",
            QuestionType.single_choice,
            "Which state did it happen in?",
            "Deadlines, fault rules, and typical values differ by state.",
            True,
            group_base,
            {},
            _STATE_OPTIONS,
        ),
        (
            "county",
            QuestionType.short_text,
            "Which county or parish?",
            "Case values vary by county, not just by state.",
            False,
            group_base,
            {"placeholder": "e.g. San Bernardino"},
            [],
        ),
        (
            "incident_date",
            QuestionType.date,
            "When did it happen?",
            None,
            True,
            None,
            {"disallow_future": True},
            [],
        ),
        (
            "release_signed",
            QuestionType.yes_no,
            "Have you already signed a release or accepted a settlement for this incident?",
            None,
            True,
            None,
            {},
            [],
        ),
    ]


def _injury_block(gap_group: int) -> list[tuple]:
    return [
        (
            "time_to_first_treatment",
            QuestionType.single_choice,
            "How soon after the incident did you first see a doctor or go to the ER?",
            None,
            True,
            None,
            {},
            [
                ("The same day", "same_day"),
                ("Within 3 days", "within_72h"),
                ("Within two weeks", "3_to_14_days"),
                ("More than two weeks later", "over_14_days"),
                ("I haven't seen a doctor", "never"),
            ],
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
            "objective_finding",
            QuestionType.single_choice,
            "Have you had imaging (X-ray, MRI, CT), and what did it show?",
            "A specific finding on imaging is the single biggest driver of case value.",
            True,
            None,
            {},
            [
                ("Yes — it showed a specific finding (fracture, herniation, tear)",
                 "imaging_positive"),
                ("Yes — it came back normal", "imaging_normal"),
                ("Yes — waiting for the results", "imaging_pending"),
                ("No imaging yet", "no_imaging"),
            ],
        ),
        (
            "finding_text",
            QuestionType.short_text,
            "If there was a finding, what did the report say — in its own words?",
            None,
            False,
            None,
            {"placeholder": "e.g. disc herniation at C5-C6"},
            [],
        ),
        (
            "treatment_level",
            QuestionType.single_choice,
            "What's the highest level of treatment you've had for this injury?",
            None,
            True,
            None,
            {},
            [
                ("No treatment", "none"),
                ("Emergency room only", "er_only"),
                ("Chiropractor or physical therapy", "conservative_care"),
                ("Pain management", "pain_management"),
                ("Injections (e.g. epidural)", "injections"),
                ("Surgery recommended in writing", "surgery_recommended_written"),
                ("Surgery performed", "surgery_performed"),
            ],
        ),
        (
            "still_treating",
            QuestionType.yes_no,
            "Are you still receiving treatment today?",
            None,
            True,
            None,
            {},
            [],
        ),
        (
            "treatment_gap_30d",
            QuestionType.yes_no,
            "Was there ever a period of 30 days or more when you stopped treatment?",
            "Insurance adjusters look for this — answering honestly lets us prepare for it.",
            True,
            gap_group,
            {},
            [],
        ),
        (
            "gap_reason",
            QuestionType.short_text,
            "If yes, why did treatment stop?",
            "A good reason (lost insurance, no provider available) softens the gap.",
            False,
            gap_group,
            {},
            [],
        ),
        (
            "future_care",
            QuestionType.single_choice,
            "Has a doctor said you will need future care?",
            None,
            True,
            None,
            {},
            [
                ("No", "none"),
                ("Yes, mentioned verbally", "recommended_verbally"),
                ("Yes, recommended in writing", "recommended_in_writing"),
            ],
        ),
        (
            "pre_existing_same_area",
            QuestionType.yes_no,
            "Had you ever injured this same body part before?",
            "The insurance company will find prior records — it's better that we know first.",
            True,
            None,
            {},
            [],
        ),
        (
            "prior_claims",
            QuestionType.single_choice,
            "Have you made injury claims or filed injury lawsuits before?",
            None,
            True,
            None,
            {},
            [("Never", "none"), ("One", "one"), ("Two or more", "two_plus")],
        ),
    ]


def _money_block(bills_group: int, wages_group: int) -> list[tuple]:
    return [
        (
            "medical_bills_amount",
            QuestionType.number,
            "Roughly how much are your medical bills so far (in dollars)?",
            None,
            False,
            bills_group,
            {"min": 0, "placeholder": "e.g. 18000"},
            [],
        ),
        (
            "medical_bills_documented",
            QuestionType.yes_no,
            "Do you have the actual bills or billing statements?",
            None,
            False,
            bills_group,
            {},
            [],
        ),
        (
            "health_payor",
            QuestionType.single_choice,
            "What insurance paid for your treatment?",
            "This determines what has to be paid back from a settlement.",
            True,
            None,
            {},
            [
                ("Private health insurance", "private"),
                ("Medicare", "medicare"),
                ("Medicaid", "medicaid"),
                ("VA / TRICARE", "tricare_va"),
                ("Auto med-pay / PIP", "medpay_pip"),
                ("The clinic is treating me on a lien / letter of protection",
                 "letter_of_protection"),
                ("I'm paying out of pocket", "none_self_pay"),
                ("Not sure", "unsure"),
            ],
        ),
        (
            "lost_wages_amount",
            QuestionType.number,
            "Roughly how much pay have you lost from missing work (in dollars)?",
            None,
            False,
            wages_group,
            {"min": 0, "placeholder": "e.g. 4000"},
            [],
        ),
        (
            "employment_type",
            QuestionType.single_choice,
            "How are you employed?",
            None,
            False,
            wages_group,
            {},
            [
                ("Employee (W-2)", "w2"),
                ("Self-employed / 1099", "self_employed_1099"),
                ("Paid in cash", "cash_unreported"),
                ("Unemployed", "unemployed"),
                ("Retired", "retired"),
                ("Student", "student"),
            ],
        ),
        (
            "wages_documentable",
            QuestionType.yes_no,
            "Can you document the lost pay (pay stubs, employer letter, tax return)?",
            None,
            False,
            wages_group,
            {},
            [],
        ),
    ]


_AUTO_QUESTIONS = [
    *_where_and_when(group_base=1),
    (
        "claimant_role",
        QuestionType.single_choice,
        "Were you the driver, a passenger, a pedestrian, or a cyclist?",
        None,
        True,
        None,
        {},
        [
            ("Driver", "driver"),
            ("Passenger", "passenger"),
            ("Pedestrian", "pedestrian"),
            ("Cyclist", "cyclist"),
        ],
    ),
    (
        "impact_type",
        QuestionType.single_choice,
        "How did the collision happen?",
        None,
        True,
        None,
        {},
        [
            ("I was rear-ended", "rear_ended"),
            ("Another driver ran a light or stop sign and hit me", "t_bone_other_ran_light"),
            ("Head-on collision", "head_on"),
            ("Sideswipe", "sideswipe"),
            ("Left-turn collision", "left_turn"),
            ("I struck another vehicle", "claimant_struck_other"),
            ("Something else", "other"),
        ],
    ),
    (
        "police_report",
        QuestionType.yes_no,
        "Did police come to the scene or was a police report filed?",
        None,
        True,
        2,
        {},
        [],
    ),
    (
        "citation_issued_to",
        QuestionType.single_choice,
        "Was anyone ticketed?",
        None,
        True,
        2,
        {},
        [
            ("The other driver", "other_party"),
            ("Me", "claimant"),
            ("Both of us", "both"),
            ("No one", "neither"),
            ("I don't know", "unknown"),
        ],
    ),
    (
        "property_damage",
        QuestionType.single_choice,
        "How bad was the damage to your vehicle?",
        None,
        True,
        None,
        {},
        [
            ("No visible damage", "none_visible"),
            ("Minor / cosmetic", "minor_cosmetic"),
            ("Moderate", "moderate"),
            ("Severe", "severe"),
            ("Totaled", "totaled"),
        ],
    ),
    (
        "commercial_defendant",
        QuestionType.yes_no,
        "Was the other driver working at the time, or driving a company or commercial vehicle?",
        "Commercial insurance policies are often 10–100× larger than personal ones.",
        True,
        None,
        {},
        [],
    ),
    (
        "um_uim_coverage",
        QuestionType.single_choice,
        "Do you have uninsured/underinsured motorist coverage on your own auto policy?",
        None,
        True,
        None,
        {},
        [("Yes", "yes"), ("No", "no"), ("Not sure", "unsure")],
    ),
    *_injury_block(gap_group=3),
    *_money_block(bills_group=4, wages_group=5),
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

_FALL_QUESTIONS = [
    *_where_and_when(group_base=1),
    (
        "location_type",
        QuestionType.single_choice,
        "Where did you fall?",
        None,
        True,
        None,
        {},
        [
            ("Retail store", "retail_store"),
            ("Grocery store", "grocery"),
            ("Restaurant", "restaurant"),
            ("Parking lot", "parking_lot"),
            ("Apartment building common area", "apartment_common_area"),
            ("Someone's home", "private_residence"),
            ("Government property", "government_property"),
            ("At my workplace", "workplace"),
            ("Somewhere else", "other"),
        ],
    ),
    (
        "claimant_status",
        QuestionType.single_choice,
        "Why were you there?",
        None,
        True,
        None,
        {},
        [
            ("I was a customer", "invitee_customer"),
            ("I was a social guest", "licensee_guest"),
            ("I live there (tenant)", "tenant"),
            ("I was making a delivery", "delivery"),
            ("I wasn't really supposed to be there", "trespasser"),
            ("Other / not sure", "unknown"),
        ],
    ),
    (
        "hazard_type",
        QuestionType.single_choice,
        "What caused the fall?",
        None,
        True,
        None,
        {},
        [
            ("Spilled liquid", "liquid_spill"),
            ("Ice or snow", "ice_snow"),
            ("Uneven surface", "uneven_surface"),
            ("Broken stair", "broken_stair"),
            ("Loose mat or rug", "loose_mat"),
            ("Something left in the walkway", "obstruction"),
            ("Poor lighting", "poor_lighting"),
            ("Missing handrail", "no_handrail"),
            ("Something else", "other"),
        ],
    ),
    (
        "hazard_duration",
        QuestionType.single_choice,
        "How long had the hazard been there before you fell?",
        "This is the make-or-break question in fall cases — the owner is only responsible "
        "if they knew or should have known about it.",
        True,
        6,
        {},
        [
            ("It had just appeared", "just_occurred"),
            ("Minutes", "minutes"),
            ("Hours", "hours"),
            ("Days or longer", "days_or_longer"),
            ("I have no idea", "unknown"),
        ],
    ),
    (
        "hazard_duration_basis",
        QuestionType.short_text,
        "How do you know that?",
        "e.g. a worker saw it earlier, the spill had dried edges, footprints ran through it.",
        False,
        6,
        {},
        [],
    ),
    (
        "staff_caused",
        QuestionType.yes_no,
        "Was the hazard caused by the property owner or an employee?",
        None,
        False,
        None,
        {},
        [],
    ),
    (
        "prior_complaints",
        QuestionType.single_choice,
        "Had anyone complained about the hazard before your fall?",
        None,
        True,
        None,
        {},
        [("Yes", "yes"), ("No", "no"), ("I don't know", "unknown")],
    ),
    (
        "warning_signs",
        QuestionType.yes_no,
        "Were there warning signs or cones near the hazard?",
        None,
        True,
        None,
        {},
        [],
    ),
    (
        "hazard_obvious",
        QuestionType.single_choice,
        "Could you have seen the hazard if you'd been looking at it?",
        None,
        True,
        None,
        {},
        [
            ("No — it was hidden", "hidden"),
            ("Partially", "partially_visible"),
            ("Yes — it was plainly visible", "plainly_visible"),
            ("Not sure", "unknown"),
        ],
    ),
    (
        "incident_report_same_day",
        QuestionType.single_choice,
        "Did you report the fall that day?",
        None,
        True,
        7,
        {},
        [
            ("Yes — a written incident report was made", "yes_written"),
            ("Yes — I told someone verbally", "yes_verbal"),
            ("No", "no"),
        ],
    ),
    (
        "photos_taken",
        QuestionType.yes_no,
        "Do you have photos of the hazard taken that day?",
        None,
        True,
        7,
        {},
        [],
    ),
    (
        "surveillance",
        QuestionType.yes_no,
        "Were there security cameras in the area?",
        "Camera footage is usually erased within 30–90 days, so this is time-critical.",
        True,
        None,
        {},
        [],
    ),
    *_injury_block(gap_group=8),
    *_money_block(bills_group=9, wages_group=10),
    (
        "description",
        QuestionType.long_text,
        "In your own words, describe what happened.",
        "What were you doing right before? What were you wearing on your feet?",
        True,
        None,
        {"placeholder": "Tell us the story of your fall…"},
        [],
    ),
]

_AUTO_SUMMARY_BODY = """Thank you for sharing the details of your auto accident.

Here's a summary of what you told us:

- Where it happened: {{county}}, {{state}}
- Date of accident: {{incident_date}}
- Your role: {{claimant_role}}
- How it happened: {{impact_type}}
- Police report: {{police_report}}
- Vehicle damage: {{property_damage}}
- First treatment: {{time_to_first_treatment}}
- Imaging: {{objective_finding}}
- Treatment level: {{treatment_level}}
- Medical bills so far: {{medical_bills_amount}}
- Lost pay: {{lost_wages_amount}}

What you described:
{{description}}

Based on cases like yours, patients in similar situations often recover settlements in the range below. This is an early, transparent estimate — not a promise."""

_FALL_SUMMARY_BODY = """Thank you for sharing the details of your fall.

Here's a summary of what you told us:

- Where it happened: {{location_type}} in {{county}}, {{state}}
- Date: {{incident_date}}
- What caused it: {{hazard_type}}
- How long the hazard was there: {{hazard_duration}}
- Reported that day: {{incident_report_same_day}}
- First treatment: {{time_to_first_treatment}}
- Imaging: {{objective_finding}}
- Treatment level: {{treatment_level}}
- Medical bills so far: {{medical_bills_amount}}

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


async def _seed_injury_type(
    db,
    *,
    slug: str,
    name: str,
    description: str,
    display_order: int,
    questions: list[tuple],
    summary_body: str,
    estimate_min: int,
    estimate_max: int,
) -> None:
    existing = await db.scalar(select(InjuryType).where(InjuryType.slug == slug))
    if existing is not None:
        print(f"Injury type '{slug}' already exists; skipping")
        return

    injury = InjuryType(
        slug=slug,
        name=name,
        description=description,
        display_order=display_order,
        is_published=True,
    )
    for order, (qslug, qtype, prompt, help_text, required, group, config, options) in enumerate(
        questions
    ):
        injury.questions.append(
            Question(
                slug=qslug,
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
        body=summary_body, estimate_min=estimate_min, estimate_max=estimate_max
    )
    db.add(injury)
    print(f"Created '{name}' injury type with seeded questionnaire")


async def main() -> None:
    async with SessionLocal() as db:
        await _seed_admin(db)
        await _seed_injury_type(
            db,
            slug="auto-accident",
            name="Auto Accident",
            description="You were involved in a car, truck, or motorcycle accident.",
            display_order=0,
            questions=_AUTO_QUESTIONS,
            summary_body=_AUTO_SUMMARY_BODY,
            estimate_min=5000,
            estimate_max=25000,
        )
        await _seed_injury_type(
            db,
            slug="slip-and-fall",
            name="Slip & Fall",
            description="You were injured in a fall on someone else's property.",
            display_order=1,
            questions=_FALL_QUESTIONS,
            summary_body=_FALL_SUMMARY_BODY,
            estimate_min=5000,
            estimate_max=25000,
        )
        inserted = await seed_jurisdiction_defaults(db)
        print(f"Jurisdiction rules: inserted {inserted} missing state rows")
        await db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
