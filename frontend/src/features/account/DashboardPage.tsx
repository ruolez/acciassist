import { useQuery } from "@tanstack/react-query";
import { Link, useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import type { CaseListItem, User } from "../../api/types";
import { formatRange, STAGE_LABELS } from "./stages";
import "./account.css";

export function DashboardPage() {
  const user = useOutletContext<User>();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["user", "cases"],
    queryFn: () => api<CaseListItem[]>("/me/cases"),
  });

  if (isLoading) return <div className="portal-empty">Loading your cases…</div>;
  if (isError || !data)
    return <div className="portal-empty error-text">We couldn&apos;t load your cases.</div>;

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
              <div className="case-card-meta">
                <span>Opened {new Date(c.created_at).toLocaleDateString()}</span>
                {formatRange(c.estimate_min, c.estimate_max) && (
                  <span className="case-card-estimate">
                    Est. {formatRange(c.estimate_min, c.estimate_max)}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
