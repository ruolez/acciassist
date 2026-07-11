import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { CaseDetail } from "../../api/types";
import { formatRange, STAGE_LABELS } from "./stages";
import { StageProgress } from "./StageProgress";
import "./account.css";

export function CaseDetailPage() {
  const { caseId } = useParams();
  const [showSummary, setShowSummary] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["user", "cases", caseId],
    queryFn: () => api<CaseDetail>(`/me/cases/${caseId}`),
    enabled: !!caseId,
  });

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

      <div className="card" style={{ padding: "var(--space-5)" }}>
        <StageProgress stage={data.stage} />
      </div>

      {range && (
        <div className="portal-section card estimate-card">
          <span className="estimate-label">Estimated settlement range</span>
          <span className="estimate-range">{range}</span>
        </div>
      )}

      <div className="portal-section">
        <h2>Updates from our team</h2>
        {updates.length === 0 ? (
          <div className="card portal-empty">
            No updates yet — we&apos;ll email you as soon as there&apos;s news.
          </div>
        ) : (
          <div className="updates-feed">
            {updates.map((u) => (
              <div
                key={u.id}
                className={`update-item ${u.kind === "stage_change" ? "stage-change" : ""}`}
              >
                <p className="update-item-body">{u.body}</p>
                <span className="update-item-date">
                  {new Date(u.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {data.summary && (
        <div className="portal-section">
          <h2>Your intake summary</h2>
          <div className="card" style={{ padding: "var(--space-5)" }}>
            {showSummary ? (
              <div className="summary-body" style={{ whiteSpace: "pre-wrap" }}>
                {data.summary.body}
              </div>
            ) : (
              <button className="btn btn-outline" onClick={() => setShowSummary(true)}>
                Show what you told us
              </button>
            )}
          </div>
        </div>
      )}

      <div className="portal-section">
        <h2>Your contact details</h2>
        <div className="card" style={{ padding: "var(--space-5)" }}>
          <p style={{ margin: 0 }}>
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
        </div>
      </div>
    </>
  );
}
