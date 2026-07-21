import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { api } from "../../api/client";
import type { InjuryType, User } from "../../api/types";
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
    body: "Plain-English questions, one at a time. Most people finish in about three minutes.",
  },
  {
    n: "03",
    title: "See what your case may be worth",
    body: "Get a clear summary of your case and an honest, no-pressure estimate of its value.",
  },
];

const VALUES = [
  {
    title: "Fully transparent",
    body: "You see every document we prepare and submit on your behalf — nothing hidden, nothing buried in fine print.",
  },
  {
    title: "Keep more of your settlement",
    body: "Personal-injury attorneys typically take a third or more of your payout. We built AcciAssist so more of it stays with you.",
  },
  {
    title: "No upfront cost",
    body: "Your assessment is free and there is nothing to buy. We only succeed when you do.",
  },
];

const FAQS = [
  {
    q: "Is the assessment really free?",
    a: "Yes. Answering the questions and seeing your summary and estimate costs nothing — no credit card, no obligation, and no pressure to continue afterwards.",
  },
  {
    q: "Do I need to create an account?",
    a: "No. You can complete the entire assessment anonymously. You only create an account if you decide you want us to work on your case, so you can follow its progress.",
  },
  {
    q: "Is my information private?",
    a: "Yes. Your answers are confidential and are used only to prepare your summary and estimate. We never sell your information, and you stay anonymous until you choose to leave your contact details.",
  },
  {
    q: "How accurate is the estimate?",
    a: "It is an honest starting range based on your answers and the rules of your state — not a promise. As you share more detail (medical records, bills, and so on), the estimate gets sharper. It is informational and not legal advice.",
  },
  {
    q: "Do I need a lawyer?",
    a: "Many injury claims are resolved without one. Our goal is to give you the full picture — what your case may be worth and what usually gets deducted — so you can decide for yourself. You are always free to consult an attorney at any point.",
  },
  {
    q: "What happens after I finish the questions?",
    a: "You immediately see a plain-English summary of your case and an estimated range. If you'd like help, leave your contact details and our team will review your case and reach out — otherwise, you can simply walk away with the information.",
  },
];

export function LandingPage() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public", "injury-types"],
    queryFn: () => api<InjuryType[]>("/injury-types"),
  });
  // Signed-in clients get "My case" instead of "Client login"; everyone else
  // 401s here, which is expected and cached.
  const { data: me } = useQuery({
    queryKey: ["user", "me"],
    queryFn: () => api<User>("/auth/me"),
    retry: false,
    staleTime: 60_000,
  });

  const scrollToBegin = () => {
    document.getElementById("begin")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="landing">
      <header className="topbar">
        <Logo size={38} withWordmark to="/" />
        <nav className="topbar-links" aria-label="Page sections">
          <a href="#how">How it works</a>
          <a href="#why">Why AcciAssist</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="topbar-actions">
          <Link className="topbar-login" to={me ? "/account" : "/login"}>
            {me ? "My case" : "Client login"}
          </Link>
          <button className="btn btn-cta topbar-cta" onClick={scrollToBegin}>
            Get my estimate
          </button>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Free injury case assessment</span>
          <h1 className="hero-title">
            Find out what your injury case is <span className="hero-em">really worth</span>
          </h1>
          <p className="hero-sub">
            Answer a few plain-English questions about your accident and get an honest
            estimate of your case&apos;s value — in about three minutes, with no login and
            no pressure.
          </p>
          <div className="hero-actions">
            <button className="btn btn-cta" onClick={scrollToBegin}>
              See what my case is worth
            </button>
            <span className="hero-note">Free &amp; confidential — no obligation</span>
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
              <span className="hero-caption-eyebrow">Patient-first care</span>
              <span className="hero-caption-text">
                Support through your recovery — nothing hidden
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="how" id="how">
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
      <section className="values" id="why">
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
          <div className="compare" role="group" aria-label="Typical attorney fees compared with AcciAssist">
            <div className="compare-col">
              <span className="compare-label">With a typical attorney</span>
              <span className="compare-big">33–40%</span>
              <p>of your settlement usually goes to contingency fees — before case costs.</p>
            </div>
            <span className="compare-divider" aria-hidden="true">
              vs
            </span>
            <div className="compare-col compare-accent">
              <span className="compare-label">With AcciAssist</span>
              <span className="compare-big">Every dollar</span>
              <p>is accounted for — you see exactly what you&apos;d keep, and why.</p>
            </div>
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

      {/* ── FAQ ── */}
      <section className="faq" id="faq">
        <div className="section-head">
          <span className="eyebrow">Common questions</span>
          <h2>Questions, answered honestly</h2>
        </div>
        <div className="faq-list">
          {FAQS.map((f) => (
            <details key={f.q} className="faq-item">
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="landing-foot">
        <div className="foot-main">
          <div className="foot-brand">
            <Logo size={30} withWordmark to="/" />
            <p className="muted">
              An honest, transparent way to understand your injury case — and keep more of
              what&apos;s yours.
            </p>
          </div>
          <nav className="foot-col" aria-label="Explore">
            <span className="foot-head">Explore</span>
            <a href="#how">How it works</a>
            <a href="#why">Why AcciAssist</a>
            <a href="#faq">FAQ</a>
            <a href="#begin">Start my assessment</a>
          </nav>
          <nav className="foot-col" aria-label="Account">
            <span className="foot-head">Account</span>
            <Link to={me ? "/account" : "/login"}>{me ? "My case" : "Client login"}</Link>
          </nav>
          <nav className="foot-col" aria-label="Legal">
            <span className="foot-head">Legal</span>
            <Link to="/privacy">Privacy policy</Link>
            <Link to="/terms">Terms of use</Link>
          </nav>
        </div>
        <p className="foot-disclaimer">
          AcciAssist provides informational estimates based on the details you share.
          AcciAssist is not a law firm and does not provide legal advice; an estimate is not
          a promise or guarantee of any settlement or outcome.
        </p>
        <p className="foot-copy">© 2026 AcciAssist. All rights reserved. Your information stays private.</p>
      </footer>
    </div>
  );
}
