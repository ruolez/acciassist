import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../../api/client";
import type { Admin } from "../../api/types";
import "./admin.css";

const KEY = ["admin", "admins"];

export function AdminsPage() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: me } = useQuery({ queryKey: ["admin", "me"], queryFn: () => api<Admin>("/admin/me") });
  const { data, isLoading } = useQuery({
    queryKey: KEY,
    queryFn: () => api<Admin[]>("/admin/admins"),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: KEY });

  const create = useMutation({
    mutationFn: () => api("/admin/admins", { method: "POST", body: { email, password } }),
    onSuccess: () => {
      setEmail("");
      setPassword("");
      setError(null);
      invalidate();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not create admin"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/admins/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Admins</h1>
      </div>

      <form
        className="card inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (email && password.length >= 8) create.mutate();
        }}
      >
        <input
          className="input"
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className="input"
          type="password"
          placeholder="Password (min 8 chars)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={!email || password.length < 8}>
          Add admin
        </button>
      </form>
      {error && <p className="error-text">{error}</p>}

      {isLoading && <p className="muted">Loading…</p>}
      <div className="table-list">
        {data?.map((admin) => (
          <div key={admin.id} className="card lead-row">
            <span className="lead-name">{admin.email}</span>
            <span className={`badge ${admin.is_active ? "badge-on" : "badge-off"}`}>
              {admin.is_active ? "active" : "inactive"}
            </span>
            <span className="muted">{new Date(admin.created_at).toLocaleDateString()}</span>
            {me && admin.id !== me.id ? (
              <button
                className="btn btn-danger"
                onClick={() => {
                  if (confirm(`Remove admin ${admin.email}?`)) remove.mutate(admin.id);
                }}
              >
                Remove
              </button>
            ) : (
              <span className="muted">you</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
