import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { Lead } from "../../api/types";
import "./admin.css";

export function LeadsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "leads"],
    queryFn: () => api<Lead[]>("/admin/leads"),
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Leads</h1>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {data && data.length === 0 && <p className="muted">No leads captured yet.</p>}
      <div className="table-list">
        {data?.map((lead) => (
          <div key={lead.id} className="card lead-row">
            <span className="lead-name">{lead.name}</span>
            <span className="muted">{lead.email}</span>
            <span className="muted">{lead.phone ?? "—"}</span>
            <span className="muted">{new Date(lead.created_at).toLocaleDateString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
