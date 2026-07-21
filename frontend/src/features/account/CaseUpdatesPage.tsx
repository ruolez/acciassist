import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api } from "../../api/client";
import { relativeTime } from "../../lib/format";
import { usePageTitle } from "../../lib/usePageTitle";
import { useCaseContext } from "./CaseLayout";
import "./account.css";

export function CaseUpdatesPage() {
  const { caseId } = useParams();
  const queryClient = useQueryClient();
  const { caseDetail: data } = useCaseContext();
  usePageTitle(`Updates · Case #${data.id}`, "AcciAssist");

  const markRead = useMutation({
    mutationFn: () => api(`/me/cases/${caseId}/updates/mark-read`, { method: "POST" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["user", "cases", caseId] }),
  });
  const markOneRead = useMutation({
    mutationFn: (updateId: number) =>
      api(`/me/cases/${caseId}/updates/${updateId}/read`, { method: "POST" }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["user", "cases", caseId] }),
  });

  const updates = [...data.updates].reverse();
  const unread = updates.filter((u) => u.read_at === null).length;

  return (
    <div className="portal-section portal-section-first">
      <div className="updates-head">
        <h2>Updates from our team</h2>
        {unread > 0 && (
          <button
            className="btn btn-outline updates-mark-read"
            disabled={markRead.isPending}
            onClick={() => markRead.mutate()}
          >
            {markRead.isPending ? "Marking…" : "Mark all as read"}
          </button>
        )}
      </div>
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
              <span
                className={`portal-timeline-dot ${u.read_at === null ? "unread" : ""}`}
                aria-hidden="true"
              />
              <div className={`update-item ${u.read_at === null ? "unread" : ""}`}>
                {u.read_at === null && <span className="update-new-chip">New</span>}
                <p className="update-item-body">{u.body}</p>
                <span className="update-item-foot">
                  <span
                    className="update-item-date"
                    title={new Date(u.created_at).toLocaleString()}
                  >
                    {relativeTime(u.created_at)}
                  </span>
                  {u.read_at === null && (
                    <button
                      className="update-read-btn"
                      disabled={markOneRead.isPending}
                      onClick={() => markOneRead.mutate(u.id)}
                    >
                      Mark as read
                    </button>
                  )}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
