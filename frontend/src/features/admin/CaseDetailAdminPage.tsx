import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { AdminCaseDetail, CaseEstimateAdmin, CaseStage } from "../../api/types";
import { CASE_STAGES, STAGE_LABELS } from "../account/stages";
import { useActionError } from "./useActionError";
import "./admin.css";

function formatUsdRange(min: number | null, max: number | null): string {
  if (min === null && max === null) return "—";
  const fmt = (n: number) => `$${n.toLocaleString()}`;
  if (min !== null && max !== null) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max)!);
}

function EstimateCard({
  sessionId,
  initial,
  onError,
}: {
  sessionId: string;
  initial: CaseEstimateAdmin | null;
  onError: (e: unknown, fallback: string) => void;
}) {
  const queryClient = useQueryClient();
  const KEY = ["admin", "ai", "estimate", sessionId];
  const { data } = useQuery({
    queryKey: KEY,
    queryFn: () => api<CaseEstimateAdmin | null>(`/admin/ai/sessions/${sessionId}/estimate`),
    initialData: initial,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 2000 : false),
  });

  const rerun = useMutation({
    mutationFn: () =>
      api<CaseEstimateAdmin>(`/admin/ai/sessions/${sessionId}/estimate/rerun`, {
        method: "POST",
      }),
    onSuccess: (pending) => queryClient.setQueryData(KEY, pending),
    onError: (e) => onError(e, "Could not re-run the estimate"),
  });

  return (
    <div className="card estimate-admin">
      <div className="estimate-admin-head">
        <h2>Estimate</h2>
        <button
          className="btn btn-outline"
          disabled={rerun.isPending || data?.status === "pending"}
          onClick={() => rerun.mutate()}
        >
          {data?.status === "pending" ? "Running…" : "Re-run estimate"}
        </button>
      </div>
      {!data && <p className="muted">No estimate yet — re-run to generate one.</p>}
      {data?.status === "pending" && <p className="muted">Calculating…</p>}
      {data?.status === "failed" && (
        <p className="error-text">Estimate failed: {data.error ?? "unknown error"}</p>
      )}
      {data?.status === "completed" && (
        <>
          <div className="estimate-admin-grid">
            <div>
              <span className="muted">Payout</span>
              <p className="estimate-admin-figure">
                {formatUsdRange(data.payout_min, data.payout_max)}
              </p>
            </div>
            <div>
              <span className="muted">Case cost</span>
              <p className="estimate-admin-figure">
                {formatUsdRange(data.case_cost_min, data.case_cost_max)}
              </p>
            </div>
            <div>
              <span className="muted">Confidence</span>
              <p>
                <span className={`badge confidence-${data.confidence ?? "low"}`}>
                  {data.confidence ?? "—"}
                </span>
              </p>
            </div>
          </div>
          {data.reasoning && <p className="estimate-admin-reasoning">{data.reasoning}</p>}
          {data.missing_info && data.missing_info.length > 0 && (
            <div>
              <span className="muted">Missing information</span>
              <ul className="estimate-admin-missing">
                {data.missing_info.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="muted estimate-admin-meta">
            {data.model} · {new Date(data.updated_at).toLocaleString()}
          </p>
        </>
      )}
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
        <EstimateCard
          sessionId={data.intake_session_id}
          initial={data.estimate}
          onError={onError}
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
