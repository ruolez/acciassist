import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { AdminClient } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { relativeTime } from "../../lib/format";
import { useActionError } from "./useActionError";
import { usePageTitle } from "../../lib/usePageTitle";
import "./admin.css";

const KEY = ["admin", "clients"];

export function ClientsPage() {
  usePageTitle("Clients");
  const queryClient = useQueryClient();
  const { error, onError, clear } = useActionError();
  const { data, isLoading } = useQuery({
    queryKey: KEY,
    queryFn: () => api<AdminClient[]>("/admin/clients"),
  });

  const remove = useMutation({
    mutationFn: ({ id, notify }: { id: number; notify: boolean }) =>
      api(`/admin/clients/${id}?notify=${notify}`, { method: "DELETE" }),
    onSuccess: () => {
      clear();
      queryClient.invalidateQueries({ queryKey: KEY });
      // Their cases, leads, and submissions were deleted with the account.
      queryClient.invalidateQueries({ queryKey: ["admin", "cases"], exact: false });
      queryClient.invalidateQueries({ queryKey: ["admin", "sessions"] });
    },
    onError: (e) => onError(e, "Could not delete the account"),
  });

  const confirmDelete = (client: AdminClient) => {
    const cases =
      client.case_count === 1 ? "1 case" : `${client.case_count} cases`;
    if (
      !confirm(
        `Delete ${client.name} (${client.email}) and their ${cases} with all documents and submissions? This cannot be undone.`,
      )
    )
      return;
    const notify = confirm(
      `Send ${client.email} an email letting them know their account was deleted?\n\nOK — send the email · Cancel — delete silently`,
    );
    remove.mutate({ id: client.id, notify });
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Clients</h1>
          <p className="page-sub">
            Every client account — invited or created — with their last sign-in.
          </p>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}
      {isLoading && <p className="muted">Loading…</p>}
      {data && data.length === 0 && (
        <EmptyState
          title="No clients yet"
          hint="A client account is created for every lead that comes in."
        />
      )}
      <div className="table-list">
        {data?.map((client) => (
          <div key={client.id} className="card lead-row">
            <span className="client-identity">
              <span className="lead-name">{client.name}</span>
              <span className="muted">{client.email}</span>
            </span>
            <span className={`badge ${client.claimed ? "badge-on" : "badge-off"}`}>
              {client.claimed ? "account created" : "invited"}
            </span>
            <span className="muted client-cases">{client.case_count} case{client.case_count === 1 ? "" : "s"}</span>
            <span
              className="muted client-login"
              title={
                client.last_login_at
                  ? new Date(client.last_login_at).toLocaleString()
                  : undefined
              }
            >
              {client.last_login_at
                ? `Last sign-in ${relativeTime(client.last_login_at)}`
                : "Never signed in"}
            </span>
            <button
              className="btn btn-danger"
              disabled={remove.isPending}
              onClick={() => confirmDelete(client)}
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
