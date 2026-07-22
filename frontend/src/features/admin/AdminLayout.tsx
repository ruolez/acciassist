import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { api } from "../../api/client";
import type { Admin } from "../../api/types";
import "./admin.css";

type IconName = "clipboard" | "inbox" | "briefcase" | "map" | "sliders" | "users";

function NavIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    clipboard: (
      <>
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
        <rect x="8" y="2" width="8" height="4" rx="1" />
        <path d="M9 12h6M9 16h6" />
      </>
    ),
    inbox: (
      <>
        <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
        <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
      </>
    ),
    briefcase: (
      <>
        <rect x="2" y="7" width="20" height="14" rx="2" />
        <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
      </>
    ),
    map: (
      <>
        <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
        <line x1="8" y1="2" x2="8" y2="18" />
        <line x1="16" y1="6" x2="16" y2="22" />
      </>
    ),
    sliders: (
      <>
        <line x1="4" y1="21" x2="4" y2="14" />
        <line x1="4" y1="10" x2="4" y2="3" />
        <line x1="12" y1="21" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12" y2="3" />
        <line x1="20" y1="21" x2="20" y2="16" />
        <line x1="20" y1="12" x2="20" y2="3" />
        <line x1="1" y1="14" x2="7" y2="14" />
        <line x1="9" y1="8" x2="15" y2="8" />
        <line x1="17" y1="16" x2="23" y2="16" />
      </>
    ),
    users: (
      <>
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </>
    ),
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
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

const NAV_SECTIONS: {
  label: string;
  items: { to: string; label: string; icon: IconName }[];
}[] = [
  {
    label: "Intake",
    items: [
      { to: "/admin/injury-types", label: "Injury Types", icon: "clipboard" },
      { to: "/admin/submissions", label: "Submissions", icon: "inbox" },
    ],
  },
  {
    label: "Clients",
    items: [
      { to: "/admin/cases", label: "Cases", icon: "briefcase" },
      { to: "/admin/clients", label: "Clients", icon: "users" },
    ],
  },
  {
    label: "Configuration",
    items: [
      { to: "/admin/jurisdictions", label: "Jurisdictions", icon: "map" },
      { to: "/admin/settings", label: "Settings", icon: "sliders" },
      { to: "/admin/admins", label: "Admins", icon: "users" },
    ],
  },
];

export function AdminLayout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [navOpen, setNavOpen] = useState(false);
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
      <header className="admin-topbar">
        <button
          className="admin-menu-btn"
          aria-label="Open navigation"
          onClick={() => setNavOpen(true)}
        >
          <svg
            viewBox="0 0 24 24"
            width="22"
            height="22"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <Logo size={28} withWordmark />
      </header>

      {navOpen && <div className="admin-scrim" onClick={() => setNavOpen(false)} />}

      <aside className={`admin-sidebar ${navOpen ? "open" : ""}`}>
        <div className="admin-brand-row">
          <Logo size={32} withWordmark />
          <span className="admin-role-chip">Admin</span>
        </div>
        <nav className="admin-nav">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="admin-nav-section">
              <span className="admin-nav-heading">{section.label}</span>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setNavOpen(false)}
                  className={({ isActive }) => `admin-nav-link ${isActive ? "active" : ""}`}
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="admin-sidebar-foot">
          <span className="admin-avatar" aria-hidden="true">
            {data.email.charAt(0).toUpperCase()}
          </span>
          <span className="admin-identity">
            <span className="admin-identity-email" title={data.email}>
              {data.email}
            </span>
            <button className="admin-logout" onClick={() => logout.mutate()}>
              Log out
            </button>
          </span>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  );
}
