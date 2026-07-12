import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useParams } from "react-router-dom";
import { z } from "zod";

import { Logo } from "../../components/Logo";
import { api, ApiError } from "../../api/client";
import type { PublicEstimate, Summary } from "../../api/types";
import "./intake.css";

const CALCULATING_TIMEOUT_MS = 45_000;

const leadSchema = z.object({
  name: z.string().min(1, "Please enter your name"),
  email: z.string().email("Enter a valid email"),
  phone: z.string().optional(),
});
type LeadForm = z.infer<typeof leadSchema>;

function formatRange(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  const fmt = (n: number) => `$${n.toLocaleString()}`;
  if (min !== null && max !== null) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max)!);
}

export function SummaryPage() {
  const { sessionId } = useParams();
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["summary", sessionId],
    queryFn: () => api<Summary>(`/intake/${sessionId}/summary`),
    enabled: !!sessionId,
  });

  // Personalized estimate: poll while it's being computed, then fall back to
  // the injury type's static range if it never completes.
  const [calcTimedOut, setCalcTimedOut] = useState(false);
  const estimateQuery = useQuery({
    queryKey: ["estimate", sessionId],
    queryFn: () => api<PublicEstimate>(`/intake/${sessionId}/estimate`),
    enabled: !!sessionId,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 2500 : false),
  });
  const estimateStatus = estimateQuery.data?.status;

  useEffect(() => {
    if (estimateStatus !== "pending") return;
    const timer = setTimeout(() => setCalcTimedOut(true), CALCULATING_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [estimateStatus]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LeadForm>({ resolver: zodResolver(leadSchema) });

  const onSubmit = async (values: LeadForm) => {
    setSubmitError(null);
    try {
      await api("/leads", {
        method: "POST",
        body: { intake_session_id: sessionId, ...values },
      });
      setSubmitted(true);
    } catch (e) {
      setSubmitError(
        e instanceof ApiError
          ? e.message
          : "We couldn't send your details. Please check your connection and try again.",
      );
    }
  };

  if (isLoading)
    return (
      <div className="wizard-bg">
        <div className="wizard-state muted">Loading your summary…</div>
      </div>
    );
  if (isError || !data)
    return (
      <div className="wizard-bg">
        <div className="wizard-state error-text">We couldn&apos;t load your summary.</div>
      </div>
    );

  const estimate = estimateQuery.data;
  const personalRange =
    estimate?.status === "completed"
      ? formatRange(estimate.payout_min, estimate.payout_max)
      : null;
  const calculating = estimate?.status === "pending" && !calcTimedOut;
  const range = personalRange ?? formatRange(data.estimate_min, data.estimate_max);

  return (
    <div className="wizard-bg">
      <div className="summary-page">
        <div className="summary-top">
          <Logo size={40} withWordmark to="/" />
        </div>
        <h1>Your wellness summary</h1>
        <p className="summary-lead">Here&apos;s what you shared with us.</p>

      <div className="card summary-card">
        <div className="summary-body">{data.body}</div>
      </div>

      {calculating ? (
        <div className="card estimate-card">
          <span className="estimate-label">Estimated settlement range</span>
          <div className="estimate-thinking" role="status" aria-live="polite">
            <span className="estimate-thinking-bar" />
            <span className="muted">Calculating your estimate…</span>
          </div>
        </div>
      ) : (
        range && (
          <div className="card estimate-card">
            <span className="estimate-label">Estimated settlement range</span>
            <span className="estimate-range">{range}</span>
            <span className="help-text">{data.estimate_note}</span>
          </div>
        )
      )}

      {submitted ? (
        <div className="card cta-card">
          <h2>Thank you!</h2>
          <p className="muted">
            Check your inbox — we&apos;ve emailed your case details and a link to create
            your account, where you can follow your case&apos;s progress. One of our
            specialists will reach out shortly.
          </p>
        </div>
      ) : (
        <div className="card cta-card">
          <h2>Ready to maximize your settlement?</h2>
          <p className="muted">
            Leave your details and we&apos;ll take it from here — transparently, with no
            upfront cost.
          </p>
          <form onSubmit={handleSubmit(onSubmit)} className="lead-form">
            <div className="field">
              <label>Full name</label>
              <input className="input" {...register("name")} />
              {errors.name && <span className="error-text">{errors.name.message}</span>}
            </div>
            <div className="field">
              <label>Email</label>
              <input className="input" type="email" {...register("email")} />
              {errors.email && <span className="error-text">{errors.email.message}</span>}
            </div>
            <div className="field">
              <label>Phone (optional)</label>
              <input className="input" {...register("phone")} />
            </div>
            {submitError && (
              <p className="error-text" role="alert">
                {submitError}
              </p>
            )}
            <button className="btn btn-cta" type="submit" disabled={isSubmitting}>
              {submitError ? "Try again →" : "Work with us →"}
            </button>
          </form>
        </div>
      )}
      </div>
    </div>
  );
}
