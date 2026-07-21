import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { CaseDocument } from "../../api/types";
import { relativeTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";
import { useCaseContext } from "./CaseLayout";
import { formatRange, STAGE_EXPLANATIONS } from "./stages";
import { StageProgress } from "./StageProgress";
import "./account.css";

export function CaseOverviewPage() {
  const { caseId } = useParams();
  const { caseDetail: data } = useCaseContext();
  usePageTitle(`Overview · Case #${data.id}`, "AcciAssist");

  const { data: docs } = useQuery({
    queryKey: ["user", "cases", caseId, "documents"],
    queryFn: () => api<CaseDocument[]>(`/me/cases/${caseId}/documents`),
    enabled: !!caseId,
  });

  const range = formatRange(data.estimate_min, data.estimate_max);
  const latest = data.updates.length > 0 ? data.updates[data.updates.length - 1] : null;

  return (
    <>
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

      <div className="snapshot-grid portal-section">
        <Link to="updates" className="card snapshot-tile">
          <span className="snapshot-label">Latest update</span>
          {latest ? (
            <>
              <p className="snapshot-body">
                {latest.body.length > 140 ? `${latest.body.slice(0, 140)}…` : latest.body}
              </p>
              <span className="muted snapshot-when">{relativeTime(latest.created_at)}</span>
            </>
          ) : (
            <p className="snapshot-body muted">
              No updates yet — we&apos;ll email you as soon as there&apos;s news.
            </p>
          )}
          <span className="snapshot-cta">
            View all updates <span aria-hidden="true">→</span>
          </span>
        </Link>
        <Link to="documents" className="card snapshot-tile">
          <span className="snapshot-label">Documents</span>
          <p className="snapshot-body">
            {docs && docs.length > 0 ? (
              <>
                {docs.length} file{docs.length === 1 ? "" : "s"} uploaded. Bills, records,
                and photos all strengthen your case.
              </>
            ) : (
              <span className="muted">
                Nothing uploaded yet — even phone photos of bills and paperwork help.
              </span>
            )}
          </p>
          <span className="snapshot-cta">
            {docs && docs.length > 0 ? "Manage documents" : "Upload documents"}{" "}
            <span aria-hidden="true">→</span>
          </span>
        </Link>
      </div>
    </>
  );
}
