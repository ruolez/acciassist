import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Outlet, useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import type { User } from "../../api/types";
import { Logo } from "../../components/Logo";
import "./account.css";

export function AccountLayout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["user", "me"],
    queryFn: () => api<User>("/auth/me"),
  });

  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.clear();
      navigate("/login");
    },
  });

  if (isLoading) return <div className="portal-empty">Loading…</div>;
  if (isError || !data) return <Navigate to="/login" replace />;

  return (
    <div className="portal-shell">
      <header className="portal-topbar">
        <Logo size={36} withWordmark to="/account" />
        <div className="portal-topbar-user">
          <span className="portal-avatar" aria-hidden="true">
            {(data.name || data.email).charAt(0).toUpperCase()}
          </span>
          <span className="portal-user-name" title={data.email}>
            {data.name ? data.name.split(" ")[0] : data.email}
          </span>
          <button className="portal-logout" onClick={() => logout.mutate()}>
            Log out
          </button>
        </div>
      </header>
      <main className="portal-main">
        <Outlet context={data satisfies User} />
      </main>
    </div>
  );
}
