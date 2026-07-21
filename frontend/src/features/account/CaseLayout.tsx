import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useOutletContext,
  useParams,
} from "react-router-dom";

import { api } from "../../api/client";
import type { CaseDetail, CaseDocument, CaseListItem, User } from "../../api/types";
import { STAGE_LABELS } from "./stages";
import "./account.css";

export type CaseOutletContext = { user: User; caseDetail: CaseDetail };

/** Typed context for pages rendered inside CaseLayout. */
export function useCaseContext(): CaseOutletContext {
  return useOutletContext<CaseOutletContext>();
}

type IconName = "home" | "file" | "bell" | "person";

function NavIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    home: (
      <>
        <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </>
    ),
    file: (
      <>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </>
    ),
    bell: (
      <>
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </>
    ),
    person: (
      <>
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </>
    ),
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

const navCls = ({ isActive }: { isActive: boolean }) =>
  `case-nav-link ${isActive ? "active" : ""}`;

export function CaseLayout() {
  const { caseId } = useParams();
  const user = useOutletContext<User>();
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["user", "cases", caseId],
    queryFn: () => api<CaseDetail>(`/me/cases/${caseId}`),
    enabled: !!caseId,
    // After the follow-up submits, the refined estimate is recalculating —
    // poll until it lands (keeps running whichever section is open).
    refetchInterval: (q) => (q.state.data?.estimate_status === "pending" ? 3000 : false),
  });
  // Same key + fetch as DocumentsSection, so the badge and the page share one
  // cache entry and upload/delete invalidation updates the badge instantly.
  const { data: docs } = useQuery({
    queryKey: ["user", "cases", caseId, "documents"],
    queryFn: () => api<CaseDocument[]>(`/me/cases/${caseId}/documents`),
    enabled: !!caseId,
  });
  // Single-case users are auto-forwarded here from /account, so an "All
  // cases" link would just bounce them back — only show it when it leads
  // somewhere meaningful.
  const { data: allCases } = useQuery({
    queryKey: ["user", "cases"],
    queryFn: () => api<CaseListItem[]>("/me/cases"),
  });
  const showAllCases = (allCases?.length ?? 0) > 1;

  if (isLoading) return <div className="portal-empty">Loading your case…</div>;
  if (isError || !data)
    return (
      <div className="portal-empty">
        <p className="error-text">We couldn&apos;t load this case.</p>
        <Link className="portal-back" to="/account">
          ← Back to your cases
        </Link>
      </div>
    );

  return (
    <div className="case-shell">
      <aside className="case-sidenav">
        {showAllCases && (
          <Link className="portal-back" to="/account">
            ← All cases
          </Link>
        )}
        <div className="case-side-head">
          <span className="case-side-title">
            {data.injury_type_name ?? "Your case"} · #{data.id}
          </span>
          <div className="case-side-meta">
            <span className={`stage-badge stage-${data.stage}`}>
              {STAGE_LABELS[data.stage]}
            </span>
            <span className="muted case-side-opened">
              Opened {new Date(data.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
        <nav className="case-nav" aria-label="Case sections">
          <NavLink to="." end className={navCls}>
            <NavIcon name="home" />
            Overview
            {data.followup_pending && (
              <span
                className="case-nav-dot"
                role="img"
                aria-label="Action needed"
                title="Action needed"
              />
            )}
          </NavLink>
          <NavLink to="documents" className={navCls}>
            <NavIcon name="file" />
            Documents
            {docs && docs.length > 0 && (
              <span className="case-nav-badge">{docs.length}</span>
            )}
          </NavLink>
          <NavLink to="updates" className={navCls}>
            <NavIcon name="bell" />
            Updates
            {data.updates.length > 0 && (
              <span className="case-nav-badge">{data.updates.length}</span>
            )}
          </NavLink>
          <NavLink to="details" className={navCls}>
            <NavIcon name="person" />
            Case details
          </NavLink>
        </nav>
        <p className="case-side-help muted">
          Questions? Reply to any email from our team — it reaches the person
          handling your case.
        </p>
      </aside>
      <div className="case-content">
        <Outlet context={{ user, caseDetail: data } satisfies CaseOutletContext} />
      </div>
    </div>
  );
}
