import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { IntakeSessionDetail, IntakeSessionSummary } from "../../api/types";
import { EmptyState } from "./EmptyState";
import { humanize, relativeTime } from "./format";
import { usePageTitle } from "./usePageTitle";
import "./admin.css";

function SubmissionDetail({ sessionId }: { sessionId: string }) {
  const { data } = useQuery({
    queryKey: ["admin", "session", sessionId],
    queryFn: () => api<IntakeSessionDetail>(`/admin/intake-sessions/${sessionId}`),
  });
  if (!data) return <p className="muted">Loading…</p>;
  const est = data.estimate;
  return (
    <div className="answer-list">
      {est && (
        <div className="answer-row submission-estimate">
          <span className="muted">Estimate</span>
          <span>
            {est.status === "completed" && (
              <>
                Payout ${est.payout_min?.toLocaleString()} – $
                {est.payout_max?.toLocaleString()} · cost $
                {est.case_cost_min?.toLocaleString()} – $
                {est.case_cost_max?.toLocaleString()} · {est.confidence} confidence
              </>
            )}
            {est.status === "pending" && "Calculating…"}
            {est.status === "failed" && (
              <span className="error-text">Failed: {est.error ?? "unknown error"}</span>
            )}
          </span>
        </div>
      )}
      {data.answers.length === 0 && <p className="muted">No answers recorded.</p>}
      {data.answers.map((a) => (
        <div key={a.question_id} className="answer-row">
          <span className="muted">#{a.question_id}</span>
          <span>{Array.isArray(a.value) ? a.value.join(", ") : String(a.value)}</span>
        </div>
      ))}
    </div>
  );
}

function EstimateCell({ s }: { s: IntakeSessionSummary }) {
  if (s.payout_min !== null && s.payout_max !== null) {
    return (
      <span className="sub-estimate">
        ${s.payout_min.toLocaleString()} – ${s.payout_max.toLocaleString()}
      </span>
    );
  }
  if (s.estimate_status === "pending") return <span className="sub-estimate none">Calculating…</span>;
  if (s.estimate_status === "failed")
    return <span className="sub-estimate none error-text">Estimate failed</span>;
  return <span className="sub-estimate none">No estimate</span>;
}

type StatusFilter = "all" | "completed" | "in_progress";

export function SubmissionsPage() {
  usePageTitle("Submissions");
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "sessions"],
    queryFn: () => api<IntakeSessionSummary[]>("/admin/intake-sessions"),
  });

  const visible = (data ?? []).filter((s) => filter === "all" || s.status === filter);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Submissions</h1>
          <p className="page-sub">Every intake questionnaire, its lead, and its AI estimate — newest first.</p>
        </div>
      </div>

      <div className="filter-chips">
        {(["all", "completed", "in_progress"] as const).map((f) => (
          <button
            key={f}
            className={`chip ${filter === f ? "chip-active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f === "all" ? "All" : humanize(f)}
          </button>
        ))}
      </div>

      {isLoading && <p className="muted">Loading…</p>}
      {data && visible.length === 0 && (
        <EmptyState
          title={filter === "all" ? "No submissions yet" : `No ${humanize(filter).toLowerCase()} submissions`}
          hint="Completed patient questionnaires appear here with their estimates as soon as they come in."
        />
      )}
      <div className="table-list">
        {visible.map((s) => (
          <div key={s.id} className="card table-row-card">
            <button className="sub-row" onClick={() => setOpen(open === s.id ? null : s.id)}>
              <span className="status-cell">
                <span className={`status-dot ${s.status}`} />
                {humanize(s.status)}
              </span>
              <span className="sub-main">
                <span className="sub-type">{s.injury_type_name ?? "Unknown type"}</span>
                <span className="sub-lead">{s.lead_name ?? "Anonymous"}</span>
              </span>
              <EstimateCell s={s} />
              <span className="sub-date" title={new Date(s.started_at).toLocaleString()}>
                {relativeTime(s.started_at)}
              </span>
              <span className="sub-chevron">{open === s.id ? "▾" : "▸"}</span>
            </button>
            {open === s.id && <SubmissionDetail sessionId={s.id} />}
          </div>
        ))}
      </div>
    </div>
  );
}
