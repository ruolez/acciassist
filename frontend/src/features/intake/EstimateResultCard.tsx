import type { PublicEstimate } from "../../api/types";
import "./intake.css";

function formatRange(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  const fmt = (n: number) => `$${n.toLocaleString()}`;
  if (min !== null && max !== null) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max)!);
}

function WarningsList({ estimate }: { estimate: PublicEstimate }) {
  if (!estimate.warnings || estimate.warnings.length === 0) return null;
  return (
    <div className="estimate-warnings">
      {estimate.warnings.map((w) => (
        <p
          key={w.code}
          className={`estimate-warning ${w.severity === "time_critical" ? "urgent" : ""}`}
        >
          {w.severity === "time_critical" ? "⚠ " : ""}
          {w.message}
        </p>
      ))}
    </div>
  );
}

function FactorList({ title, items }: { title: string; items: string[] | null }) {
  if (!items || items.length === 0) return null;
  return (
    <details className="estimate-factors">
      <summary>{title}</summary>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </details>
  );
}

/**
 * Patient-facing estimate presentation.
 *
 * - pending (calculating) → animated placeholder
 * - completed + gated → explanation card, no dollar range, no static fallback
 * - completed with a pipeline result → gross + net + factors + warnings
 * - completed legacy row / failed / none → static template range fallback
 */
export function EstimateResultCard({
  estimate,
  calculating,
  fallbackMin,
  fallbackMax,
  fallbackNote,
  firstLook = false,
}: {
  estimate: PublicEstimate | undefined;
  calculating: boolean;
  fallbackMin: number | null;
  fallbackMax: number | null;
  fallbackNote: string;
  /** Frames the range as a broad first estimate from the initial questions. */
  firstLook?: boolean;
}) {
  if (calculating) {
    return (
      <div className="card estimate-card">
        <span className="estimate-label">Estimated settlement range</span>
        <div className="estimate-thinking" role="status" aria-live="polite">
          <span className="estimate-thinking-bar" />
          <span className="muted">Calculating your estimate…</span>
        </div>
      </div>
    );
  }

  if (estimate?.status === "completed" && estimate.gated) {
    return (
      <div className="card estimate-card estimate-gated">
        <span className="estimate-label">About your estimate</span>
        <h3 className="estimate-gated-title">{estimate.gated.title}</h3>
        <p className="estimate-gated-text">{estimate.gated.explanation}</p>
        <WarningsList estimate={estimate} />
        {estimate.disclaimer && <p className="estimate-disclaimer">{estimate.disclaimer}</p>}
      </div>
    );
  }

  const isPipelineResult =
    estimate?.status === "completed" &&
    estimate.disclaimer !== null &&
    // A zero range reads as an insult, not an estimate — use the static
    // fallback presentation instead.
    (estimate.payout_max ?? 0) > 0;
  if (estimate?.status === "completed" && isPipelineResult) {
    const gross = formatRange(estimate.payout_min, estimate.payout_max);
    // Never show the patient a $0 net: hide the box when nothing survives the
    // deductions, and soften "$0 – $X" into "Up to $X".
    const net =
      (estimate.net_max ?? 0) <= 0
        ? null
        : estimate.net_min === 0
          ? `Up to $${estimate.net_max!.toLocaleString()}`
          : formatRange(estimate.net_min, estimate.net_max);
    return (
      <div className="card estimate-card estimate-full">
        <span className="estimate-label">
          {firstLook ? "Your first estimate" : "Estimated settlement range"}
        </span>
        <span className="estimate-range">{gross ?? "—"}</span>
        {firstLook && (
          <span className="help-text">
            A broad first look based on your initial answers — it narrows once we know
            more details.
          </span>
        )}
        {net && (
          <div className="estimate-net">
            <span className="estimate-net-label">Estimated in your pocket</span>
            <span className="estimate-net-range">{net}</span>
            <span className="help-text">
              After our {estimate.fee_pct_assumed ?? 10}% service fee, case costs, and
              estimated medical liens — no attorney taking a 33–40% cut.
            </span>
          </div>
        )}
        <WarningsList estimate={estimate} />
        <FactorList title="What strengthens your case" items={estimate.drivers} />
        {/* During onboarding we haven't asked for documents yet, so missing
            documentation is framed as upside, not criticism. */}
        {!firstLook && (
          <FactorList title="What could reduce your estimate" items={estimate.reducers} />
        )}
        {estimate.improvements && estimate.improvements.length > 0 && (
          <div className="estimate-improvements">
            <span className="estimate-improvements-title">
              {firstLook
                ? "How your estimate improves from here"
                : "What would most improve this estimate"}
            </span>
            {firstLook && (
              <p className="estimate-improvements-lead">
                We haven&apos;t asked for your documents yet — that happens after you
                sign up. As we receive these, your case gets stronger and your estimate
                more precise:
              </p>
            )}
            <ul>
              {estimate.improvements.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {estimate.disclaimer && <p className="estimate-disclaimer">{estimate.disclaimer}</p>}
      </div>
    );
  }

  // Legacy completed rows (pre-pipeline) still carry a payout range; zero
  // ranges fall back to the static template instead of showing "$0 – $0".
  const range =
    (estimate?.status === "completed" && (estimate.payout_max ?? 0) > 0
      ? formatRange(estimate.payout_min, estimate.payout_max)
      : null) ?? formatRange(fallbackMin, fallbackMax);
  if (!range) return null;
  return (
    <div className="card estimate-card">
      <span className="estimate-label">Estimated settlement range</span>
      <span className="estimate-range">{range}</span>
      <span className="help-text">{fallbackNote}</span>
    </div>
  );
}
