import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { CaseDetail } from "../../api/types";
import { relativeTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";
import { DocumentsSection } from "./DocumentsSection";
import { formatRange, STAGE_EXPLANATIONS, STAGE_LABELS } from "./stages";
import { StageProgress } from "./StageProgress";
import "./account.css";

export function CaseDetailPage() {
  const { caseId } = useParams();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["user", "cases", caseId],
    queryFn: () => api<CaseDetail>(`/me/cases/${caseId}`),
    enabled: !!caseId,
    // After the follow-up submits, the refined estimate is recalculating —
    // poll until it lands.
    refetchInterval: (q) => (q.state.data?.estimate_status === "pending" ? 3000 : false),
  });
  usePageTitle(
    data ? `${data.injury_type_name ?? "Your case"} · #${data.id}` : "Your case",
  );

  if (isLoading) return <div className="portal-empty">Loading your case…</div>;
  if (isError || !data)
    return <div className="portal-empty error-text">We couldn&apos;t load this case.</div>;

  const range = formatRange(data.estimate_min, data.estimate_max);
  const updates = [...data.updates].reverse();

  return (
    <>
      <Link className="portal-back" to="/account">
        ← All cases
      </Link>
      <h1>
        {data.injury_type_name ?? "Your case"} · #{data.id}
      </h1>
      <p className="portal-sub">
        Opened {new Date(data.created_at).toLocaleDateString()} · Current status:{" "}
        <strong>{STAGE_LABELS[data.stage]}</strong>
      </p>

      <div className="card stage-card">
        <StageProgress stage={data.stage} />
        <p className="stage-explainer">
          <strong>What&apos;s happening now:</strong> {STAGE_EXPLANATIONS[data.stage]}
        </p>
      </div>

      {data.followup_pending && (
        <div className="portal-section card followup-cta">
          <div>
            <h2>Sharpen your estimate</h2>
            <p className="muted">
              Your current estimate is a broad first look. {data.followup_total} short
              follow-up question{data.followup_total === 1 ? "" : "s"} about
              documentation and details will narrow it down.
            </p>
          </div>
          <Link className="btn btn-cta" to={`/account/cases/${data.id}/follow-up`}>
            Answer follow-up questions
          </Link>
        </div>
      )}

      {data.estimate_status === "pending" && (
        <div className="portal-section card portal-recalc">
          <span className="estimate-thinking-bar" />
          <span className="muted">
            Recalculating your estimate with your new answers…
          </span>
        </div>
      )}

      {range && data.estimate_status !== "pending" && (
        <div className="portal-section card estimate-card">
          <span className="estimate-label">
            Estimated settlement range
            {data.estimate_refined && (
              <span className="refined-chip">Refined with your follow-up answers ✓</span>
            )}
          </span>
          <span className="estimate-range">{range}</span>
          {data.followup_pending && (
            <span className="help-text">
              A broad first estimate — answering the follow-up questions narrows it.
            </span>
          )}
          <span className="estimate-disclaimer">
            Estimates are informational, based on what you&apos;ve shared — not a promise
            of any outcome.
          </span>
        </div>
      )}

      <DocumentsSection caseId={String(data.id)} />

      <div className="portal-section">
        <h2>Updates from our team</h2>
        {updates.length === 0 ? (
          <div className="card portal-empty">
            No updates yet — we&apos;ll email you as soon as there&apos;s news.
          </div>
        ) : (
          <div className="portal-timeline">
            {updates.map((u) => (
              <div
                key={u.id}
                className={`portal-timeline-item ${u.kind === "stage_change" ? "stage-change" : ""}`}
              >
                <span className="portal-timeline-dot" aria-hidden="true" />
                <div className="update-item">
                  <p className="update-item-body">{u.body}</p>
                  <span
                    className="update-item-date"
                    title={new Date(u.created_at).toLocaleString()}
                  >
                    {relativeTime(u.created_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {data.summary && (
        <div className="portal-section">
          <h2>Your intake summary</h2>
          <details className="card summary-details">
            <summary>Show what you told us</summary>
            <div className="summary-body">{data.summary.body}</div>
          </details>
        </div>
      )}

      <div className="portal-section">
        <h2>Your contact details</h2>
        <div className="card contact-card">
          <p className="contact-lines">
            {data.name}
            <br />
            {data.email}
            {data.phone && (
              <>
                <br />
                {data.phone}
              </>
            )}
          </p>
          <p className="muted contact-note">
            This is how we reach you about your case. If anything changes, reply to any
            of our emails and we&apos;ll update it.
          </p>
        </div>
      </div>
    </>
  );
}
