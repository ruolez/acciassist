"""Stage 2 — deterministic gates and warnings (code, never the model).

A blocking gate zeroes the estimate regardless of how the damages math would
have come out; the model is never allowed to reason its way around one.
Non-blocking warnings surface time-critical duties (SOL windows,
notice-of-claim deadlines, surveillance preservation).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.services.estimate_pipeline.canonical import CanonicalExtraction

SOL_WARNING_WINDOW_DAYS = 120
_DAYS_PER_YEAR = 365.25


@dataclass
class GateWarning:
    code: str
    severity: str  # 'time_critical' | 'caution' | 'info'
    message: str
    deadline: date | None = None


@dataclass
class GateResult:
    blocked: bool = False
    code: str | None = None
    title: str | None = None
    explanation: str | None = None
    warnings: list[GateWarning] = field(default_factory=list)


def sol_expiry(incident: date, sol_years: float) -> date:
    return incident + timedelta(days=round(sol_years * _DAYS_PER_YEAR))


def _passes_no_fault_threshold(x: CanonicalExtraction) -> bool:
    """Facts that plausibly clear a serious-injury tort threshold. Anything
    less stays inside PIP in a no-fault state."""
    ladder = x.injury.treatment_ladder
    return (
        x.injury.objective_finding.status == "imaging_positive"
        or ladder.highest_reached
        in ("injections", "surgery_recommended_written", "surgery_performed")
        or (ladder.impairment_rating_pct or 0) > 0
        or x.gates.fatality_involved is True
    )


def evaluate_gates(x: CanonicalExtraction, rule, today: date) -> GateResult:
    """``rule`` is a JurisdictionRule (or None when the state is unknown);
    only attribute access is used so tests can pass a stub."""
    warnings: list[GateWarning] = []

    def blocked(code: str, title: str, explanation: str) -> GateResult:
        return GateResult(True, code, title, explanation, warnings)

    if x.meta.state is None:
        warnings.append(
            GateWarning(
                "state_unknown",
                "caution",
                "The state where this happened was not provided. Deadlines, fault rules, "
                "and damage caps all depend on it, so this estimate is much less certain.",
            )
        )

    if x.gates.government_defendant is True:
        warnings.append(
            GateWarning(
                "notice_of_claim",
                "time_critical",
                "Claims against a government entity usually require a formal notice of "
                "claim within months of the incident — often far sooner than the normal "
                "lawsuit deadline. Act quickly.",
            )
        )

    if (
        x.liability.evidence.surveillance_exists is True
        and x.liability.evidence.surveillance_preservation_sent is not True
    ):
        warnings.append(
            GateWarning(
                "preserve_surveillance",
                "time_critical",
                "Security footage is routinely overwritten within 30–90 days. Send a "
                "written preservation request to the property owner immediately.",
            )
        )

    if x.injury.treatment_gap.duration_bucket in ("30_to_59_days", "60_plus_days"):
        warnings.append(
            GateWarning(
                "treatment_gap",
                "caution",
                "A gap of 30+ days in treatment is one of the first things an insurance "
                "adjuster uses to argue the injury was minor or unrelated.",
            )
        )

    if x.gates.release_signed is True:
        return blocked(
            "release_signed",
            "A release or settlement has already been signed",
            "Once a release is signed or a settlement accepted, the claim is almost "
            "always over. An attorney can review whether any exception applies, but no "
            "dollar estimate is meaningful.",
        )

    if x.gates.fatality_involved is True:
        return blocked(
            "wrongful_death",
            "A death is involved",
            "Cases involving a death are wrongful-death claims, which follow a "
            "different legal framework than this estimate covers. Speak with an "
            "attorney directly.",
        )

    if x.gates.workplace_injury is True:
        return blocked(
            "workers_comp",
            "This appears to be a workplace injury",
            "Injuries in the course of work are generally covered exclusively by "
            "workers' compensation, not a personal-injury lawsuit. A workers'-comp "
            "claim has its own benefits and deadlines — this estimate does not apply.",
        )

    if x.gates.claimant_status_premises == "trespasser":
        return blocked(
            "trespasser_status",
            "Legal status on the property blocks a typical claim",
            "Property owners owe little duty of care to someone who was not permitted "
            "to be there. Recovery is rare absent willful harm; no meaningful dollar "
            "estimate can be given.",
        )

    if rule is not None and x.meta.incident_date is not None:
        expiry = sol_expiry(x.meta.incident_date, rule.sol_years_pi)
        if expiry < today:
            note = f" {rule.sol_note}" if rule.sol_note else ""
            return blocked(
                "sol_expired",
                "The filing deadline appears to have passed",
                f"{rule.state_name}'s statute of limitations for personal-injury claims "
                f"is about {rule.sol_years_pi:g} years, which puts the deadline near "
                f"{expiry.isoformat()}. Deadlines can have exceptions (tolling, "
                f"discovery rules), so confirm with an attorney immediately — but as "
                f"stated, the claim is likely time-barred.{note}",
            )
        if expiry <= today + timedelta(days=SOL_WARNING_WINDOW_DAYS):
            warnings.append(
                GateWarning(
                    "sol_approaching",
                    "time_critical",
                    f"The filing deadline in {rule.state_name} is approximately "
                    f"{expiry.isoformat()} — within the next few months. Talk to an "
                    "attorney now.",
                    deadline=expiry,
                )
            )

    if (
        rule is not None
        and rule.no_fault
        and x.meta.case_type == "motor_vehicle"
        and not _passes_no_fault_threshold(x)
    ):
        threshold = f" {rule.pip_threshold_note}" if rule.pip_threshold_note else ""
        return blocked(
            "no_fault_threshold",
            f"{rule.state_name} is a no-fault state",
            "In a no-fault state, injuries that do not cross the serious-injury "
            "threshold are compensated through your own PIP coverage, and a separate "
            "injury claim is usually worth little or nothing. Nothing you described "
            "(no objective imaging finding, no injections or surgery, no permanent "
            f"impairment) clears that threshold as stated.{threshold}",
        )

    return GateResult(warnings=warnings)
