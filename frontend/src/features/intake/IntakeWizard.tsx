import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { api } from "../../api/client";
import type { AnswerValue, IntakeStart } from "../../api/types";
import { QuestionRenderer } from "./QuestionRenderer";
import { boundsError, isPageComplete, progressPercent } from "./wizard-logic";
import "./intake.css";

type Stored = {
  start: IntakeStart;
  answers: Record<number, AnswerValue>;
  pageIndex: number;
};

const storageKey = (injuryTypeId: string) => `acci_intake_${injuryTypeId}`;

export function IntakeWizard() {
  const { injuryTypeId } = useParams();
  const navigate = useNavigate();
  const [start, setStart] = useState<IntakeStart | null>(null);
  const [answers, setAnswers] = useState<Record<number, AnswerValue>>({});
  const [pageIndex, setPageIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const initialized = useRef(false);

  // Start a fresh session or resume one stored in localStorage.
  useEffect(() => {
    if (!injuryTypeId || initialized.current) return;
    initialized.current = true;
    const cached = localStorage.getItem(storageKey(injuryTypeId));
    if (cached) {
      const parsed: Stored = JSON.parse(cached);
      setStart(parsed.start);
      setAnswers(parsed.answers);
      setPageIndex(parsed.pageIndex);
      return;
    }
    api<IntakeStart>("/intake/start", {
      method: "POST",
      body: { injury_type_id: Number(injuryTypeId) },
    })
      .then((data) => setStart(data))
      .catch(() => setError("We couldn't start your questionnaire. Please go back and retry."));
  }, [injuryTypeId]);

  // Persist progress so a reload resumes where the patient left off.
  useEffect(() => {
    if (!injuryTypeId || !start) return;
    const payload: Stored = { start, answers, pageIndex };
    localStorage.setItem(storageKey(injuryTypeId), JSON.stringify(payload));
  }, [injuryTypeId, start, answers, pageIndex]);

  if (error) {
    return (
      <div className="wizard-bg">
        <div className="wizard-state">
          <p className="error-text">{error}</p>
          <button className="btn btn-outline" onClick={() => navigate("/")}>
            ← Back to start
          </button>
        </div>
      </div>
    );
  }

  if (!start) {
    return (
      <div className="wizard-bg">
        <div className="wizard-state muted">Loading…</div>
      </div>
    );
  }

  const page = start.pages[pageIndex];
  const isLast = pageIndex === start.total_pages - 1;
  const canAdvance = isPageComplete(page.questions, answers);

  const setAnswer = (questionId: number, value: AnswerValue) =>
    setAnswers((prev) => ({ ...prev, [questionId]: value }));

  async function next() {
    if (!start || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/intake/${start.session_id}/answers`, {
        method: "POST",
        body: {
          answers: page.questions
            .filter((q) => answers[q.id] !== undefined)
            .map((q) => ({ question_id: q.id, value: answers[q.id] })),
        },
      });
      if (isLast) {
        await api(`/intake/${start.session_id}/complete`, { method: "POST" });
        localStorage.removeItem(storageKey(injuryTypeId!));
        navigate(`/intake/session/${start.session_id}/summary`);
      } else {
        setPageIndex((i) => i + 1);
      }
    } catch {
      setError("We couldn't save your answer. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="wizard-bg">
      <div className="wizard">
        <div className="wizard-top">
          <Logo size={32} withWordmark to="/" />
          <div className="wizard-step">
            {pageIndex + 1} / {start.total_pages}
          </div>
        </div>
      <div className="progress">
        <div
          className="progress-fill"
          style={{ width: `${progressPercent(pageIndex, start.total_pages)}%` }}
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
              value={answers[q.id] ?? null}
              onChange={(v) => setAnswer(q.id, v)}
            />
            {boundsError(q, answers[q.id] ?? null) && (
              <p className="error-text" role="alert">
                {boundsError(q, answers[q.id] ?? null)}
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="wizard-nav">
        <button
          className="btn btn-ghost"
          onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
          disabled={pageIndex === 0 || busy}
        >
          ← Back
        </button>
          <button className="btn btn-cta" onClick={next} disabled={!canAdvance || busy}>
            {isLast ? "See my summary" : "Next →"}
          </button>
        </div>
      </div>
    </div>
  );
}
