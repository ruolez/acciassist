import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import type { CaseListItem, User } from "../../api/types";
import { relativeTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";
import { CASE_STAGES, formatRange, STAGE_LABELS } from "./stages";
import "./account.css";

function StageMeter({ stage }: { stage: CaseListItem["stage"] }) {
  const current = CASE_STAGES.indexOf(stage);
  return (
    <div
      className="stage-meter"
      role="img"
      aria-label={`Stage ${current + 1} of ${CASE_STAGES.length}: ${STAGE_LABELS[stage]}`}
    >
      {CASE_STAGES.map((s, i) => (
        <span
          key={s}
          className={`stage-meter-seg ${i < current ? "done" : i === current ? "current" : ""}`}
        />
      ))}
    </div>
  );
}

export function DashboardPage() {
  usePageTitle("Your cases", "AcciAssist");
  const user = useOutletContext<User>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["user", "cases"],
    queryFn: () => api<CaseListItem[]>("/me/cases"),
  });

  if (isLoading) return <div className="portal-empty">Loading your cases…</div>;
  if (isError || !data)
    return <div className="portal-empty error-text">We couldn&apos;t load your cases.</div>;

  // One case (the common path): skip the list and land in it directly. The
  // sidebar's "All cases" link still reaches this page for the empty state.
  if (data.length === 1) return <Navigate to={`/account/cases/${data[0].id}`} replace />;

  return (
    <>
      <h1>Welcome back, {user.name.split(" ")[0]}</h1>
      <p className="portal-sub">
        {data.length === 1
          ? "Here's where your case stands."
          : `You have ${data.length} cases with us.`}
      </p>
      {data.length === 0 ? (
        <div className="card portal-empty">
          <p>You don&apos;t have any cases yet.</p>
          <Link className="btn btn-cta" to="/">
            Start a case
          </Link>
        </div>
      ) : (
        <div className="case-list">
          {data.map((c) => (
            <Link key={c.id} to={`/account/cases/${c.id}`} className="card case-card">
              <div className="case-card-head">
                <span className="case-card-title">
                  {c.injury_type_name ?? "Your case"} · #{c.id}
                </span>
                <span className={`stage-badge stage-${c.stage}`}>
                  {STAGE_LABELS[c.stage]}
                </span>
              </div>
              <StageMeter stage={c.stage} />
              {c.latest_update_body && (
                <p className="case-card-update">
                  <span className="case-card-update-label">Latest update</span>
                  {c.latest_update_body.length > 140
                    ? `${c.latest_update_body.slice(0, 140)}…`
                    : c.latest_update_body}
                  {c.latest_update_at && (
                    <span className="case-card-update-when">
                      {" "}
                      · {relativeTime(c.latest_update_at)}
                    </span>
                  )}
                </p>
              )}
              <div className="case-card-meta">
                <span>Opened {new Date(c.created_at).toLocaleDateString()}</span>
                {formatRange(c.estimate_min, c.estimate_max) && (
                  <span className="case-card-estimate">
                    Est. {formatRange(c.estimate_min, c.estimate_max)}
                  </span>
                )}
                {c.followup_pending && (
                  <span className="followup-badge">Follow-up available</span>
                )}
                <span className="case-card-open">
                  View case <span aria-hidden="true">→</span>
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}

      <div className="card help-card">
        <h2>Questions about your case?</h2>
        <p className="muted">
          Reply to any email from our team and it will reach the person handling your
          case. We read everything.
        </p>
      </div>
    </>
  );
}
