import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import type { InjuryType } from "../../api/types";
import "./intake.css";

export function LandingPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public", "injury-types"],
    queryFn: () => api<InjuryType[]>("/injury-types"),
  });

  return (
    <div className="landing">
      <header className="landing-hero">
        <div className="brand">AcciAssist</div>
        <h1>Get the settlement you deserve — transparently.</h1>
        <p className="landing-sub">
          Answer a few questions about what happened. We&apos;ll show you a clear summary
          and an honest estimate of what your case may be worth. No pressure, no login.
        </p>
      </header>

      <section className="landing-types">
        <h2>What happened to you?</h2>
        {isLoading && <p className="muted">Loading…</p>}
        {isError && <p className="error-text">Something went wrong. Please try again.</p>}
        {data && data.length === 0 && (
          <p className="muted">No case types are available yet. Please check back soon.</p>
        )}
        <div className="type-grid">
          {data?.map((it) => (
            <button
              key={it.id}
              className="type-card"
              onClick={() => navigate(`/intake/${it.id}`)}
            >
              <span className="type-name">{it.name}</span>
              {it.description && <span className="type-desc">{it.description}</span>}
              <span className="type-cta">Start →</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
