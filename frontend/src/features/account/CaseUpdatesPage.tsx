import { relativeTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";
import { useCaseContext } from "./CaseLayout";
import "./account.css";

export function CaseUpdatesPage() {
  const { caseDetail: data } = useCaseContext();
  usePageTitle(`Updates · Case #${data.id}`, "AcciAssist");

  const updates = [...data.updates].reverse();

  return (
    <div className="portal-section portal-section-first">
      <h2>Updates from our team</h2>
      {updates.length === 0 ? (
        <div className="card portal-empty">
          No updates yet — we&apos;ll email you as soon as there&apos;s news.
        </div>
      ) : (
        <div className="portal-timeline">
          {updates.map((u) => (
            <div
              key={u.id}
              className={`portal-timeline-item ${u.kind === "stage_change" ? "stage-change" : ""}`}
            >
              <span className="portal-timeline-dot" aria-hidden="true" />
              <div className="update-item">
                <p className="update-item-body">{u.body}</p>
                <span
                  className="update-item-date"
                  title={new Date(u.created_at).toLocaleString()}
                >
                  {relativeTime(u.created_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
