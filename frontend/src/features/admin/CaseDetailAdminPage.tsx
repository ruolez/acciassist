import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { AdminCaseDetail, CaseEstimateAdmin, CaseStage, Question } from "../../api/types";
import { CASE_STAGES, STAGE_LABELS } from "../account/stages";
import { AdviceCard } from "./AdviceCard";
import { PipelineEstimateCard } from "./PipelineEstimateCard";
import { useActionError } from "./useActionError";
import "./admin.css";

function EstimateGapCard({
  sessionId,
  injuryTypeId,
}: {
  sessionId: string;
  injuryTypeId: number;
}) {
  // Watches the same query the estimate card polls, so the gap list always
  // reflects the latest run.
  const { data: estimate } = useQuery({
    queryKey: ["admin", "ai", "estimate", sessionId],
    queryFn: () => api<CaseEstimateAdmin | null>(`/admin/ai/sessions/${sessionId}/estimate`),
  });
  const { data: questions } = useQuery({
    queryKey: ["admin", "questions", injuryTypeId],
    queryFn: () => api<Question[]>(`/admin/injury-types/${injuryTypeId}/questions`),
  });

  const gaps = estimate?.status === "completed" ? (estimate.missing_info ?? []) : [];
  if (gaps.length === 0) return null;

  return (
    <div className="gap-card">
      <div className="card gap-list-card">
        <h2>Missing information from this estimate</h2>
        <p className="muted">
          These facts were missing or undocumented and widened the estimate&apos;s range.
        </p>
        <ul className="gap-list">
          {gaps.map((g) => (
            <li key={g}>{g}</li>
          ))}
        </ul>
      </div>
      <AdviceCard
        injuryTypeId={injuryTypeId}
        questions={questions}
        title="Close the questionnaire gaps"
        description="Ask the AI to draft questions that would collect the missing information above, then review and add them to the questionnaire. New questions apply to future intakes only — this patient's answers don't change."
        generatePath={`/admin/ai/sessions/${sessionId}/estimate/propose-questions`}
        generateLabel="Propose questions for the gaps"
      />
    </div>
  );
}

export function CaseDetailAdminPage() {
  const { caseId } = useParams();
  const queryClient = useQueryClient();
  const [updateBody, setUpdateBody] = useState("");
  const { error, onError, clear } = useActionError();

  const KEY = ["admin", "cases", "detail", caseId];
  const { data, isLoading } = useQuery({
    queryKey: KEY,
    queryFn: () => api<AdminCaseDetail>(`/admin/cases/${caseId}`),
    enabled: !!caseId,
  });

  const refresh = (detail: AdminCaseDetail) => {
    clear();
    queryClient.setQueryData(KEY, detail);
    queryClient.invalidateQueries({ queryKey: ["admin", "cases"], exact: false });
  };

  const changeStage = useMutation({
    mutationFn: (stage: CaseStage) =>
      api<AdminCaseDetail>(`/admin/cases/${caseId}`, { method: "PATCH", body: { stage } }),
    onSuccess: refresh,
    onError: (e) => onError(e, "Could not change the stage"),
  });

  const postUpdate = useMutation({
    mutationFn: () =>
      api<AdminCaseDetail>(`/admin/cases/${caseId}/updates`, {
        method: "POST",
        body: { body: updateBody },
      }),
    onSuccess: (detail) => {
      setUpdateBody("");
      refresh(detail);
    },
    onError: (e) => onError(e, "Could not post the update"),
  });

  const resendInvite = useMutation({
    mutationFn: () => api(`/admin/cases/${caseId}/resend-invite`, { method: "POST" }),
    onSuccess: clear,
    onError: (e) => onError(e, "Could not resend the invite"),
  });

  if (isLoading) return <div className="page muted">Loading…</div>;
  if (!data) return <div className="page error-text">Case not found.</div>;

  const updates = [...data.updates].reverse();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <Link to="/admin/cases" className="muted">
            ← Cases
          </Link>
          <h1>
            Case #{data.id} · {data.lead_name}
          </h1>
        </div>
        <label className="stage-select">
          <span className="muted">Stage</span>
          <select
            className="select"
            value={data.stage}
            disabled={changeStage.isPending}
            onChange={(e) => changeStage.mutate(e.target.value as CaseStage)}
          >
            {CASE_STAGES.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="error-text">{error}</p>}

      <div className="card case-info">
        <div>
          <span className="muted">Client</span>
          <p>
            {data.lead_name}
            <br />
            {data.lead_email}
            {data.lead_phone && (
              <>
                <br />
                {data.lead_phone}
              </>
            )}
          </p>
        </div>
        <div>
          <span className="muted">Injury type</span>
          <p>{data.injury_type_name ?? "—"}</p>
        </div>
        <div>
          <span className="muted">Account</span>
          <p>
            {data.user_claimed ? (
              "Created"
            ) : (
              <button
                className="btn btn-outline"
                disabled={resendInvite.isPending}
                onClick={() => resendInvite.mutate()}
              >
                {resendInvite.isSuccess ? "Invite sent ✓" : "Resend invite email"}
              </button>
            )}
          </p>
        </div>
        <div>
          <span className="muted">Intake</span>
          <p>
            {data.intake_session_id ? (
              <Link to="/admin/submissions">View submission</Link>
            ) : (
              "—"
            )}
          </p>
        </div>
      </div>

      {data.intake_session_id && (
        <PipelineEstimateCard
          sessionId={data.intake_session_id}
          initial={data.estimate}
          onError={onError}
        />
      )}
      {data.intake_session_id && data.injury_type_id && (
        <EstimateGapCard
          sessionId={data.intake_session_id}
          injuryTypeId={data.injury_type_id}
        />
      )}

      <div className="card update-composer">
        <h2>Post an update</h2>
        <p className="muted">The client will be notified by email and can read it in their portal.</p>
        <textarea
          className="textarea"
          rows={3}
          value={updateBody}
          onChange={(e) => setUpdateBody(e.target.value)}
          placeholder="e.g. We've requested your medical records from the clinic."
        />
        <button
          className="btn btn-primary"
          disabled={!updateBody.trim() || postUpdate.isPending}
          onClick={() => postUpdate.mutate()}
        >
          Post update
        </button>
      </div>

      <div className="table-list">
        {updates.length === 0 && <p className="muted">No updates yet.</p>}
        {updates.map((u) => (
          <div key={u.id} className={`card update-row ${u.kind}`}>
            <p className="update-row-body">{u.body}</p>
            <span className="muted">
              {u.admin_email ?? "system"} · {new Date(u.created_at).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
