import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import type { AdminCaseListItem, CaseStage } from "../../api/types";
import { CASE_STAGES, STAGE_LABELS } from "../account/stages";
import { EmptyState } from "../../components/EmptyState";
import { usePageTitle } from "../../lib/usePageTitle";
import "./admin.css";

export function CasesPage() {
  usePageTitle("Cases");
  const [stageFilter, setStageFilter] = useState<CaseStage | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "cases", stageFilter],
    queryFn: () =>
      api<AdminCaseListItem[]>(`/admin/cases${stageFilter ? `?stage=${stageFilter}` : ""}`),
  });

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Cases</h1>
          <p className="page-sub">Every captured lead, its intake, account status, and progress stage.</p>
        </div>
      </div>

      <div className="filter-chips">
        <button
          className={`chip ${stageFilter === null ? "chip-active" : ""}`}
          onClick={() => setStageFilter(null)}
        >
          All
        </button>
        {CASE_STAGES.map((s) => (
          <button
            key={s}
            className={`chip ${stageFilter === s ? "chip-active" : ""}`}
            onClick={() => setStageFilter(s)}
          >
            {STAGE_LABELS[s]}
          </button>
        ))}
      </div>

      {isLoading && <p className="muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState
          title={stageFilter ? `No ${STAGE_LABELS[stageFilter].toLowerCase()} cases` : "No cases yet"}
          hint="A case is created automatically whenever a patient leaves their contact details after an assessment."
        />
      )}
      <div className="table-list">
        {data?.map((c) => (
          <Link key={c.id} to={`/admin/cases/${c.id}`} className="card lead-row case-row">
            <span className="lead-name">
              #{c.id} · {c.lead_name}
            </span>
            <span className={`badge stage-${c.stage}`}>{STAGE_LABELS[c.stage]}</span>
            <span className="muted">{c.injury_type_name ?? "—"}</span>
            <span className="muted">{c.lead_email}</span>
            <span className={`badge ${c.user_claimed ? "badge-on" : "badge-off"}`}>
              {c.user_claimed ? "account" : "no account"}
            </span>
            <span className="muted">{new Date(c.created_at).toLocaleDateString()}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
