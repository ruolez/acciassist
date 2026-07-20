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

  const isPipelineResult = estimate?.status === "completed" && estimate.disclaimer !== null;
  if (estimate?.status === "completed" && isPipelineResult) {
    const gross = formatRange(estimate.payout_min, estimate.payout_max);
    const net = formatRange(estimate.net_min, estimate.net_max);
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
              After an assumed {estimate.fee_pct_assumed ?? 33.3}% attorney fee, case costs,
              and estimated medical liens.
            </span>
          </div>
        )}
        <WarningsList estimate={estimate} />
        <FactorList title="What strengthens your case" items={estimate.drivers} />
        <FactorList title="What could reduce your estimate" items={estimate.reducers} />
        {estimate.improvements && estimate.improvements.length > 0 && (
          <div className="estimate-improvements">
            <span className="estimate-improvements-title">
              What would most improve this estimate
            </span>
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

  // Legacy completed rows (pre-pipeline) still carry a payout range.
  const range =
    (estimate?.status === "completed"
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
