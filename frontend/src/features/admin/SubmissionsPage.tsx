import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { IntakeSessionDetail, IntakeSessionSummary } from "../../api/types";
import "./admin.css";

function SubmissionDetail({ sessionId }: { sessionId: string }) {
  const { data } = useQuery({
    queryKey: ["admin", "session", sessionId],
    queryFn: () => api<IntakeSessionDetail>(`/admin/intake-sessions/${sessionId}`),
  });
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <div className="answer-list">
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

export function SubmissionsPage() {
  const [open, setOpen] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "sessions"],
    queryFn: () => api<IntakeSessionSummary[]>("/admin/intake-sessions"),
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Submissions</h1>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {data && data.length === 0 && <p className="muted">No submissions yet.</p>}
      <div className="table-list">
        {data?.map((s) => (
          <div key={s.id} className="card table-row-card">
            <button
              className="table-row"
              onClick={() => setOpen(open === s.id ? null : s.id)}
            >
              <span className={`badge ${s.status === "completed" ? "badge-on" : "badge-off"}`}>
                {s.status}
              </span>
              <span className="muted mono">{s.id.slice(0, 8)}</span>
              <span className="muted">{new Date(s.started_at).toLocaleString()}</span>
              <span>{open === s.id ? "▾" : "▸"}</span>
            </button>
            {open === s.id && <SubmissionDetail sessionId={s.id} />}
          </div>
        ))}
      </div>
    </div>
  );
}
