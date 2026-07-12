"""Baseline per-state legal parameters for the estimate pipeline.

Compiled from public sources as a starting point ONLY — every row is seeded
with ``needs_review=True`` and MUST be verified by a licensed attorney before
production reliance. Comparative-negligence regimes, statutes of limitations
and damage caps change (e.g. Florida's 2023 tort reform, Louisiana's 2024 SOL
change); admins maintain these rows in the admin UI, and the seeder never
overwrites an existing row.

comparative_rule values:
  pure          — recovery reduced by claimant's fault, never barred
  modified_50   — barred when claimant fault >= 50%
  modified_51   — barred when claimant fault >= 51% (may recover at exactly 50%)
  contributory  — any claimant fault can bar recovery entirely
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JurisdictionRule

COMPARATIVE_RULES = ("pure", "modified_50", "modified_51", "contributory")

# (code, name, comparative_rule, no_fault, pip_threshold_note, sol_years,
#  sol_note, noneconomic_cap, cap_note, collateral_source_note)
_R = [
    ("AL", "Alabama", "contributory", False, None, 2.0, None, None, None, None),
    ("AK", "Alaska", "pure", False, None, 2.0, None, 400000,
     "Non-economic cap $400k or life-expectancy formula; higher for severe permanent impairment.", None),
    ("AZ", "Arizona", "pure", False, None, 2.0, None, None,
     "Damage caps prohibited by state constitution.", None),
    ("AR", "Arkansas", "modified_50", False, None, 3.0, None, None, None, None),
    ("CA", "California", "pure", False, None, 2.0, None, None,
     "MICRA caps apply to medical-malpractice only.",
     "Howell rule: medical damages limited to amounts actually paid, not billed."),
    ("CO", "Colorado", "modified_50", False, None, 2.0,
     "3 years for motor-vehicle claims.", 729790,
     "General non-economic cap, inflation-adjusted; doubled on clear and convincing evidence. 2023-24 legislation raised caps — verify current figure.", None),
    ("CT", "Connecticut", "modified_51", False, None, 2.0, None, None, None,
     "Collateral-source reduction after verdict."),
    ("DE", "Delaware", "modified_51", False, None, 2.0, None, None, None, None),
    ("DC", "District of Columbia", "contributory", False,
     "Optional no-fault: claimant may elect PIP within 60 days, limiting tort rights.", 3.0,
     None, None, None, None),
    ("FL", "Florida", "modified_51", True,
     "Non-economic damages require permanent injury, significant scarring, or death (serious-injury threshold).", 2.0,
     "2 years for causes accruing on/after 3/24/2023 (HB 837); 4 years before.", None, None,
     "Mandatory collateral-source setoff (Medicare/Medicaid excepted)."),
    ("GA", "Georgia", "modified_50", False, None, 2.0, None, None, None, None),
    ("HI", "Hawaii", "modified_51", True,
     "Tort threshold: PIP benefits exhausted ($5,000+) or significant permanent injury.", 2.0,
     None, 375000, "Pain-and-suffering cap $375k with broad exceptions (verify applicability).", None),
    ("ID", "Idaho", "modified_50", False, None, 2.0, None, 500000,
     "Non-economic cap inflation-adjusted from $250k (2004); ~$500k+ today — verify current figure. No cap for reckless/felonious acts.", None),
    ("IL", "Illinois", "modified_51", False, None, 2.0, None, None,
     "Caps held unconstitutional.", None),
    ("IN", "Indiana", "modified_51", False, None, 2.0, None, None, None, None),
    ("IA", "Iowa", "modified_51", False, None, 2.0, None, None,
     "Med-mal non-economic caps only.", None),
    ("KS", "Kansas", "modified_50", True,
     "Tort threshold: $2,000 medical or fracture/permanent injury/disfigurement.", 2.0,
     None, None, "General non-economic cap struck down (Hilburn, 2019).", None),
    ("KY", "Kentucky", "pure", True,
     "Choice no-fault: $1,000 medical / fracture / permanent injury threshold unless tort rights were retained in writing.", 1.0,
     "2 years from injury or last PIP payment for motor-vehicle claims under the no-fault act.",
     None, "Damage caps prohibited by state constitution.", None),
    ("LA", "Louisiana", "pure", False, None, 2.0,
     "2 years for torts on/after 7/1/2024; 1 year before.", None, None, None),
    ("ME", "Maine", "modified_50", False, None, 6.0, None, None, None, None),
    ("MD", "Maryland", "contributory", False, None, 3.0, None, 950000,
     "Non-economic cap increases $15k each October; ~$950k for 2025 causes — verify current figure.", None),
    ("MA", "Massachusetts", "modified_51", True,
     "Tort threshold: $2,000 reasonable medical expenses or fracture/permanency/disfigurement.", 3.0,
     None, None, None, None),
    ("MI", "Michigan", "modified_51", True,
     "Non-economic damages require death, serious impairment of body function, or permanent serious disfigurement.", 3.0,
     None, None,
     "Comparative fault >50% bars non-economic damages only; economic damages reduced proportionally.", None),
    ("MN", "Minnesota", "modified_51", True,
     "Tort threshold: $4,000 medical (excluding imaging) or 60+ days disability / permanent injury/disfigurement.", 6.0,
     "Commonly cited 6 years for negligence PI, 2 years for intentional torts — verify.", None, None, None),
    ("MS", "Mississippi", "pure", False, None, 3.0, None, 1000000,
     "Non-economic cap $1M in all civil actions.", None),
    ("MO", "Missouri", "pure", False, None, 5.0, None, None,
     "General caps held unconstitutional; med-mal caps reinstated by statute.", None),
    ("MT", "Montana", "modified_51", False, None, 3.0, None, None, None, None),
    ("NE", "Nebraska", "modified_50", False, None, 4.0, None, None, None, None),
    ("NV", "Nevada", "modified_51", False, None, 2.0, None, None,
     "Med-mal caps only.", None),
    ("NH", "New Hampshire", "modified_51", False, None, 3.0, None, None,
     "Caps held unconstitutional.", None),
    ("NJ", "New Jersey", "modified_51", True,
     "Choice no-fault: 'limitation on lawsuit' (verbal threshold) requires permanent injury unless the full-tort option was purchased.", 2.0,
     None, None, None, None),
    ("NM", "New Mexico", "pure", False, None, 3.0, None, None, None, None),
    ("NY", "New York", "pure", True,
     "Serious-injury threshold (Ins. Law §5102(d)): fracture, significant disfigurement, permanent limitation, or 90/180-day impairment.", 3.0,
     None, None, None, "CPLR 4545: collateral sources offset against verdict."),
    ("NC", "North Carolina", "contributory", False, None, 3.0, None, None, None, None),
    ("ND", "North Dakota", "modified_50", True,
     "Tort threshold: $2,500 medical or serious injury (60+ days disability, disfigurement, death).", 6.0,
     None, None, None, None),
    ("OH", "Ohio", "modified_51", False, None, 2.0, None, None,
     "Non-economic cap $250k/$350k for non-catastrophic injuries (tort reform) — verify applicability.", None),
    ("OK", "Oklahoma", "modified_51", False, None, 2.0, None, None,
     "General non-economic cap struck down (Beason, 2019).", None),
    ("OR", "Oregon", "modified_51", False, None, 2.0, None, None,
     "$500k non-economic cap held unconstitutional for most injury claims; applies in wrongful death.", None),
    ("PA", "Pennsylvania", "modified_51", True,
     "Choice no-fault: limited-tort electors need 'serious injury' for non-economic damages; full-tort electors unrestricted.", 2.0,
     None, None, "Caps prohibited by state constitution (except vs. Commonwealth).", None),
    ("RI", "Rhode Island", "pure", False, None, 3.0, None, None, None, None),
    ("SC", "South Carolina", "modified_51", False, None, 3.0, None, None, None, None),
    ("SD", "South Dakota", "modified_50", False, None, 3.0,
     "Unique 'slight/gross' rule: claimant recovers only if their negligence was slight compared to defendant's — stricter than a standard 50% bar.",
     None, None, None),
    ("TN", "Tennessee", "modified_50", False, None, 1.0, None, 750000,
     "Non-economic cap $750k ($1M catastrophic).", None),
    ("TX", "Texas", "modified_51", False, None, 2.0, None, None,
     "Med-mal caps only; punitive damages capped.", None),
    ("UT", "Utah", "modified_50", True,
     "Tort threshold: $3,000 medical or permanent disability/impairment/disfigurement.", 4.0,
     None, None, "Med-mal caps only.", None),
    ("VT", "Vermont", "modified_51", False, None, 3.0, None, None, None, None),
    ("VA", "Virginia", "contributory", False, None, 2.0, None, None,
     "Med-mal total cap only.", None),
    ("WA", "Washington", "pure", False, None, 3.0, None, None,
     "Caps held unconstitutional.", None),
    ("WV", "West Virginia", "modified_51", False, None, 2.0, None, None,
     "Med-mal caps only.", None),
    ("WI", "Wisconsin", "modified_51", False, None, 3.0, None, None,
     "Med-mal caps only.", None),
    ("WY", "Wyoming", "modified_51", False, None, 4.0, None, None,
     "Caps prohibited by state constitution.", None),
]

JURISDICTION_DEFAULTS: list[dict] = [
    {
        "state_code": code,
        "state_name": name,
        "comparative_rule": rule,
        "no_fault": no_fault,
        "pip_threshold_note": pip_note,
        "sol_years_pi": sol,
        "sol_note": sol_note,
        "noneconomic_cap": cap,
        "cap_note": cap_note,
        "collateral_source_note": cs_note,
        "needs_review": True,
    }
    for code, name, rule, no_fault, pip_note, sol, sol_note, cap, cap_note, cs_note in _R
]

STATE_NAMES_TO_CODES = {name.lower(): code for code, name, *_ in _R}
STATE_CODES = {code for code, *_ in _R}


async def seed_jurisdiction_defaults(db: AsyncSession) -> int:
    """Insert any missing state rows; never touch existing (admin-edited)
    rows. Returns the number of rows inserted. Safe to re-run."""
    existing = set(await db.scalars(select(JurisdictionRule.state_code)))
    inserted = 0
    for row in JURISDICTION_DEFAULTS:
        if row["state_code"] in existing:
            continue
        db.add(JurisdictionRule(**row))
        inserted += 1
    return inserted
