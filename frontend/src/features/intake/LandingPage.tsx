import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { api } from "../../api/client";
import type { InjuryType } from "../../api/types";
import "./landing.css";

const REASSURANCE = ["No login required", "About 3 minutes", "Private & secure"];

function TypeIcon({ slug, name }: { slug: string; name: string }) {
  const key = `${slug} ${name}`.toLowerCase();
  const isAuto = /(auto|car|vehicle|truck|motor|collision|accident)/.test(key);
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      width="24"
      height="24"
      aria-hidden="true"
    >
      {isAuto ? (
        <>
          <path d="M5 11l1.4-4.2A2 2 0 0 1 8.3 5.4h7.4a2 2 0 0 1 1.9 1.4L19 11" />
          <path d="M3.5 11h17a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-1.2a1 1 0 0 1-1-1v-.8H6.7v.8a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1z" />
          <circle cx="7.2" cy="14" r="1" />
          <circle cx="16.8" cy="14" r="1" />
        </>
      ) : (
        <path d="M3 12h3.5l1.8 5 3.7-11 2.2 8 1.3-2H21" />
      )}
    </svg>
  );
}

const STEPS = [
  {
    n: "01",
    title: "Tell us what happened",
    body: "Choose the type of accident or injury you experienced. No account needed.",
  },
  {
    n: "02",
    title: "Answer a few questions",
    body: "Simple questions, one at a time. Most people finish in about three minutes.",
  },
  {
    n: "03",
    title: "See your summary",
    body: "Get a clear overview of your case and an honest estimate of what it may be worth.",
  },
];

const VALUES = [
  {
    title: "Fully transparent",
    body: "You see every document we prepare and submit on your behalf — nothing hidden.",
  },
  {
    title: "Keep more of your settlement",
    body: "No greedy cuts. We help you maximize your payout instead of shrinking it.",
  },
  {
    title: "No upfront cost",
    body: "Start your assessment for free. We only succeed when you do.",
  },
];

export function LandingPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public", "injury-types"],
    queryFn: () => api<InjuryType[]>("/injury-types"),
  });

  const scrollToBegin = () => {
    document.getElementById("begin")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="landing">
      <header className="topbar">
        <Logo size={42} withWordmark to="/" />
        <nav className="topbar-nav">
          <span className="topbar-tag">Patient Intake</span>
          <button className="btn btn-cta topbar-cta" onClick={scrollToBegin}>
            Start here
          </button>
        </nav>
      </header>

      {/* ── Hero ── */}
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Physical wellness &amp; recovery</span>
          <h1 className="hero-title">
            Your path to <span className="hero-em">complete wellness</span> starts here
          </h1>
          <p className="hero-sub">
            Count on our expertise in physical wellness — specialists who help you move
            better, recover faster, and feel like yourself again.
          </p>
          <div className="hero-actions">
            <button className="btn btn-cta" onClick={scrollToBegin}>
              Start here
            </button>
            <span className="hero-note">Free, no-obligation assessment</span>
          </div>
          <ul className="reassurance">
            {REASSURANCE.map((item) => (
              <li key={item}>
                <span className="reassurance-dot" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div className="hero-visual">
          <span className="hero-glow" aria-hidden="true" />
          <div className="hero-frame">
            <img src="/hero.png" alt="A clinician caring for two smiling children" />
            <div className="hero-caption">
              <span className="hero-caption-eyebrow">Trusted care</span>
              <span className="hero-caption-text">
                Compassionate, expert physical wellness
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="how">
        <div className="section-head">
          <span className="eyebrow">How it works</span>
          <h2>From uncertain to confident, in minutes</h2>
          <p className="muted">
            A guided process that respects your time and keeps you in control the whole way.
          </p>
        </div>
        <ol className="steps">
          {STEPS.map((s) => (
            <li key={s.n} className="step">
              <span className="step-num">{s.n}</span>
              <h3>{s.title}</h3>
              <p className="muted">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* ── Why us / values ── */}
      <section className="values">
        <div className="values-inner">
          <div className="section-head">
            <span className="eyebrow eyebrow-light">Why AcciAssist</span>
            <h2>Transparent care that puts you first</h2>
            <p>
              We believe you deserve the full picture — and the full value of your claim.
            </p>
          </div>
          <div className="value-grid">
            {VALUES.map((v) => (
              <div key={v.title} className="value-card">
                <span className="value-mark" aria-hidden="true" />
                <h3>{v.title}</h3>
                <p>{v.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Begin: choose injury type (the action) ── */}
      <section className="begin" id="begin">
        <div className="section-head">
          <span className="eyebrow">Get started</span>
          <h2>What brought you here today?</h2>
          <p className="muted">
            Choose what happened, and we&apos;ll guide you through a few simple questions —
            one at a time.
          </p>
        </div>

        {isLoading && <p className="muted begin-state">Loading your options…</p>}
        {isError && (
          <p className="error-text begin-state">
            We couldn&apos;t load the options right now. Please refresh and try again.
          </p>
        )}
        {data && data.length === 0 && (
          <p className="muted begin-state">No assessments are available yet. Please check back soon.</p>
        )}

        <div className="type-grid">
          {data?.map((it, i) => (
            <button
              key={it.id}
              className="type-card"
              style={{ animationDelay: `${i * 70}ms` }}
              onClick={() => navigate(`/intake/${it.id}`)}
            >
              <span className="type-icon">
                <TypeIcon slug={it.slug} name={it.name} />
              </span>
              <span className="type-name">{it.name}</span>
              {it.description && <span className="type-desc">{it.description}</span>}
              <span className="type-cta">
                Begin <span className="type-arrow">→</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <footer className="landing-foot">
        <Logo size={28} withWordmark to="/" />
        <span className="muted">
          Transparent, patient-first care. Your information stays private.
        </span>
      </footer>
    </div>
  );
}
