import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import type { Admin } from "../../api/types";
import "./admin.css";

const NAV = [
  { to: "/admin/injury-types", label: "Injury Types" },
  { to: "/admin/submissions", label: "Submissions" },
  { to: "/admin/cases", label: "Cases" },
  { to: "/admin/admins", label: "Admins" },
  { to: "/admin/settings", label: "Settings" },
];

export function AdminLayout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "me"],
    queryFn: () => api<Admin>("/admin/me"),
  });

  const logout = useMutation({
    mutationFn: () => api("/admin/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.clear();
      navigate("/admin/login");
    },
  });

  if (isLoading) return <div className="admin-loading muted">Loading…</div>;
  if (isError || !data) return <Navigate to="/admin/login" replace />;

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">AcciAssist</div>
        <div className="admin-role">Admin</div>
        <nav className="admin-nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `admin-nav-link ${isActive ? "active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="admin-sidebar-foot">
          <span className="muted">{data.email}</span>
          <button className="btn btn-ghost" onClick={() => logout.mutate()}>
            Log out
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}
