import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Logo } from "../../components/Logo";
import { api, ApiError } from "../../api/client";
import type { AnswerValue, IntakeStart } from "../../api/types";
import { QuestionRenderer } from "./QuestionRenderer";
import {
  boundsError,
  isPageComplete,
  progressPercent,
  reconcileStoredState,
} from "./wizard-logic";
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

  // Start a fresh session or resume one stored in localStorage. A cached
  // snapshot may be stale — the admin can edit questions at any time — so it
  // is always revalidated against the server before use.
  useEffect(() => {
    if (!injuryTypeId || initialized.current) return;
    initialized.current = true;

    const startFresh = () =>
      api<IntakeStart>("/intake/start", {
        method: "POST",
        body: { injury_type_id: Number(injuryTypeId) },
      })
        .then((data) => {
          setStart(data);
          setAnswers({});
          setPageIndex(0);
        })
        .catch(() =>
          setError("We couldn't start your questionnaire. Please go back and retry."),
        );

    const cached = localStorage.getItem(storageKey(injuryTypeId));
    if (!cached) {
      startFresh();
      return;
    }
    const parsed: Stored = JSON.parse(cached);
    api<IntakeStart>(`/intake/${parsed.start.session_id}/pages`)
      .then((fresh) => {
        const fitted = reconcileStoredState(parsed.answers, parsed.pageIndex, fresh);
        setStart(fresh);
        setAnswers(fitted.answers);
        setPageIndex(fitted.pageIndex);
      })
      .catch(() => {
        // Cached session is gone or unusable — abandon it and start over.
        localStorage.removeItem(storageKey(injuryTypeId));
        startFresh();
      });
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
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        // The questionnaire changed under us (e.g. a question was edited or
        // removed). Drop the stale snapshot and reload into a clean state.
        localStorage.removeItem(storageKey(injuryTypeId!));
        setError(
          "This questionnaire was just updated and your earlier answers no longer fit. " +
            "Please start again — it only takes a moment.",
        );
      } else {
        setError("We couldn't save your answer. Please try again.");
      }
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
