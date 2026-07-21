import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError } from "../../api/client";
import type { AnswerValue, Followup } from "../../api/types";
import { QuestionRenderer } from "../intake/QuestionRenderer";
import { boundsError, isPageComplete, progressPercent } from "../intake/wizard-logic";
import "../intake/intake.css";
import { usePageTitle } from "../../lib/usePageTitle";
import "./account.css";

/** Portal follow-up wizard: the detail questions that narrow the estimate.
 * Answers live server-side (loaded with the questionnaire), so patients can
 * leave and resume from any device. */
export function FollowupPage() {
  usePageTitle("Follow-up questions");
  const { caseId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [started, setStarted] = useState(false);
  const [pageIndex, setPageIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, AnswerValue> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["user", "followup", caseId],
    queryFn: () => api<Followup>(`/me/cases/${caseId}/follow-up`),
    enabled: !!caseId,
    staleTime: Infinity,
  });

  if (isLoading) return <div className="portal-empty">Loading your follow-up…</div>;
  if (isError || !data)
    return (
      <div className="portal-empty error-text">We couldn&apos;t load the follow-up.</div>
    );
  if (data.completed || data.total_pages === 0) {
    return (
      <div className="portal-empty">
        {data.completed
          ? "You've already completed the follow-up — thank you!"
          : "There are no follow-up questions for your case right now."}{" "}
        <Link to={`/account/cases/${caseId}`}>Back to your case</Link>
      </div>
    );
  }

  const current = answers ?? data.answers;
  const page = data.pages[pageIndex];
  const canAdvance = isPageComplete(page.questions, current);
  const isLast = pageIndex === data.total_pages - 1;

  const setAnswer = (qid: number, value: AnswerValue) =>
    setAnswers({ ...current, [qid]: value });

  const next = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/me/cases/${caseId}/follow-up/answers`, {
        method: "POST",
        body: {
          answers: page.questions
            .filter((q) => current[q.id] !== undefined)
            .map((q) => ({ question_id: q.id, value: current[q.id] })),
        },
      });
      if (isLast) {
        await api(`/me/cases/${caseId}/follow-up/complete`, { method: "POST" });
        queryClient.invalidateQueries({ queryKey: ["user", "cases"], exact: false });
        queryClient.invalidateQueries({ queryKey: ["user", "followup", caseId] });
        navigate(`/account/cases/${caseId}`);
      } else {
        setPageIndex((i) => i + 1);
      }
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "We couldn't save your answers — try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!started) {
    return (
      <div className="followup-intro card">
        <h1>Sharpen your estimate</h1>
        <p>
          Your first estimate was intentionally broad — it came from just the essentials.
          These {countQuestions(data)} short questions cover the details insurance
          companies actually look at: documentation, treatment history, and coverage.
        </p>
        <p className="muted">
          The more of them you answer, the narrower and more dependable your estimate
          becomes. You can leave and come back any time — your answers are saved as you
          go.
        </p>
        <div className="followup-intro-actions">
          <button className="btn btn-cta" onClick={() => setStarted(true)}>
            Start — about {Math.max(2, Math.round(countQuestions(data) / 4))} minutes
          </button>
          <Link className="btn btn-ghost" to={`/account/cases/${caseId}`}>
            Not now
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="followup-wizard">
      <div className="followup-head">
        <Link className="portal-back" to={`/account/cases/${caseId}`}>
          ← Back to your case
        </Link>
        <div className="wizard-step">
          {pageIndex + 1} / {data.total_pages}
        </div>
      </div>
      <div className="progress">
        <div
          className="progress-fill"
          style={{ width: `${progressPercent(pageIndex, data.total_pages)}%` }}
        />
      </div>

      <div className="wizard-body">
        {page.questions.map((q) => (
          <div key={q.id} className="wizard-question">
            <h2 className="wizard-prompt">
              {q.prompt}
              {q.is_required && <span className="req">*</span>}
            </h2>
            {q.help_text && <p className="help-text">{q.help_text}</p>}
            <QuestionRenderer
              question={q}
              value={current[q.id] ?? null}
              onChange={(v) => setAnswer(q.id, v)}
              autoFocus={false}
            />
            {boundsError(q, current[q.id] ?? null) && (
              <p className="error-text" role="alert">
                {boundsError(q, current[q.id] ?? null)}
              </p>
            )}
          </div>
        ))}
      </div>

      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      <div className="wizard-nav">
        <button
          className="btn btn-ghost"
          onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
          disabled={pageIndex === 0 || busy}
        >
          ← Back
        </button>
        <button className="btn btn-cta" onClick={next} disabled={!canAdvance || busy}>
          {isLast ? "Submit & refine my estimate" : "Next →"}
        </button>
      </div>
    </div>
  );
}

function countQuestions(data: Followup): number {
  return data.pages.reduce((n, p) => n + p.questions.length, 0);
}
