import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ApiError } from "../../api/client";
import type { EstimateAdvice, Question } from "../../api/types";
import { groupIntoPages } from "./page-layout";
import { PageLayoutList } from "./PageLayoutList";
import { QuestionEditor, type QuestionDraft } from "./QuestionEditor";
import { useActionError } from "./useActionError";
import "./admin.css";

function AdviceCard({ injuryTypeId }: { injuryTypeId: number }) {
  const queryClient = useQueryClient();
  const KEY = ["admin", "ai", "advice", injuryTypeId];
  const [adviceError, setAdviceError] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: KEY,
    queryFn: () => api<EstimateAdvice | null>(`/admin/ai/injury-types/${injuryTypeId}/advice`),
  });

  const generate = useMutation({
    mutationFn: () =>
      api<EstimateAdvice>(`/admin/ai/injury-types/${injuryTypeId}/advice`, { method: "POST" }),
    onSuccess: (advice) => {
      setAdviceError(null);
      queryClient.setQueryData(KEY, advice);
    },
    onError: (e) =>
      setAdviceError(
        e instanceof ApiError && e.code === "ai_not_configured"
          ? "Configure the OpenRouter key and model in Settings first."
          : e instanceof ApiError
            ? e.message
            : "Could not get AI recommendations",
      ),
  });

  return (
    <div className="card advice-card">
      <div className="advice-head">
        <div>
          <h2>AI recommendations</h2>
          <p className="muted">
            Ask the AI what this questionnaire should collect for accurate case cost and
            payout estimates.
          </p>
        </div>
        <button
          className="btn btn-outline"
          disabled={generate.isPending}
          onClick={() => generate.mutate()}
        >
          {generate.isPending
            ? "Asking…"
            : data
              ? "Regenerate"
              : "Ask AI what's needed"}
        </button>
      </div>
      {adviceError && <p className="error-text">{adviceError}</p>}
      {data && (
        <>
          <pre className="advice-content">{data.content}</pre>
          <p className="muted advice-meta">
            {data.model} · {new Date(data.updated_at).toLocaleString()}
          </p>
        </>
      )}
    </div>
  );
}

const TYPE_SHORT: Record<string, string> = {
  single_choice: "single",
  multi_choice: "multi",
  short_text: "text",
  number: "number",
  date: "date",
  yes_no: "yes/no",
  long_text: "long text",
};

export function QuestionnaireBuilder() {
  const { id } = useParams();
  const injuryTypeId = Number(id);
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const { error, onError, clear } = useActionError();

  const selectGuarded = (next: number | "new" | null) => {
    if (next === selected) return;
    if (editorDirty && !confirm("Discard unsaved changes to this question?")) return;
    setSelected(next);
  };

  const key = ["admin", "questions", injuryTypeId];
  const { data: questions } = useQuery({
    queryKey: key,
    queryFn: () => api<Question[]>(`/admin/injury-types/${injuryTypeId}/questions`),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: key });

  const create = useMutation({
    mutationFn: (draft: QuestionDraft) =>
      api<Question>(`/admin/injury-types/${injuryTypeId}/questions`, {
        method: "POST",
        body: draft,
      }),
    onSuccess: (q) => {
      setSelected(q.id);
      clear();
      invalidate();
    },
    onError: (e) => onError(e, "Could not create the question"),
  });

  const update = useMutation({
    mutationFn: ({ qid, draft }: { qid: number; draft: QuestionDraft }) =>
      api(`/admin/injury-types/${injuryTypeId}/questions/${qid}`, {
        method: "PUT",
        body: draft,
      }),
    onSuccess: () => {
      clear();
      invalidate();
    },
    onError: (e) => onError(e, "Could not save the question"),
  });

  const remove = useMutation({
    mutationFn: (qid: number) =>
      api(`/admin/injury-types/${injuryTypeId}/questions/${qid}`, { method: "DELETE" }),
    onSuccess: () => {
      setSelected(null);
      clear();
      invalidate();
    },
    onError: (e) => onError(e, "Could not delete the question"),
  });

  const layout = useMutation({
    mutationFn: (pages: number[][]) =>
      api(`/admin/injury-types/${injuryTypeId}/questions/layout`, {
        method: "PUT",
        body: { pages },
      }),
    onSuccess: () => {
      clear();
      invalidate();
    },
    onError: (e) => {
      onError(e, "Could not save the page layout — it was restored");
      invalidate();
    },
  });

  const selectedQuestion =
    typeof selected === "number" ? questions?.find((q) => q.id === selected) ?? null : null;

  const saving = create.isPending || update.isPending;

  const handleSave = (draft: QuestionDraft) => {
    if (selected === "new" || selected === null) {
      create.mutate(draft);
    } else {
      update.mutate({ qid: selected, draft });
    }
  };

  const handleDuplicate = () => {
    if (!selectedQuestion) return;
    const { placeholder, min, max, max_length, disallow_future } =
      selectedQuestion.config ?? {};
    create.mutate({
      type: selectedQuestion.type,
      prompt: `${selectedQuestion.prompt} (copy)`,
      help_text: selectedQuestion.help_text,
      is_required: selectedQuestion.is_required,
      config: { placeholder, min, max, max_length, disallow_future },
      options: selectedQuestion.options.map((o) => ({ label: o.label, value: o.value })),
    });
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <Link className="back-link" to="/admin/injury-types">
            ← Injury Types
          </Link>
          <h1>Questionnaire</h1>
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}

      <div className="builder">
        <div className="builder-list card">
          <div className="builder-list-head">
            <span>Questions</span>
            <button className="btn btn-outline" onClick={() => selectGuarded("new")}>
              + Add
            </button>
          </div>
          {questions && questions.length === 0 && (
            <p className="muted builder-empty">No questions yet. Click “+ Add”.</p>
          )}
          {questions && questions.length > 0 && (
            <PageLayoutList
              pages={groupIntoPages(questions)}
              onLayoutChange={(pages) => layout.mutate(pages)}
              renderItem={(q) => (
                <button
                  className={`q-item ${selected === q.id ? "active" : ""}`}
                  onClick={() => selectGuarded(q.id)}
                >
                  <span className="q-prompt">{q.prompt || "(untitled)"}</span>
                  <span className="q-type">{TYPE_SHORT[q.type]}</span>
                </button>
              )}
            />
          )}
        </div>

        <div className="builder-editor card">
          {selected === null ? (
            <p className="muted builder-empty">Select a question or add a new one.</p>
          ) : (
            <QuestionEditor
              key={selected}
              initial={selectedQuestion}
              saving={saving}
              onSave={handleSave}
              onDelete={
                typeof selected === "number" ? () => remove.mutate(selected) : undefined
              }
              onDuplicate={typeof selected === "number" ? handleDuplicate : undefined}
              onDirtyChange={setEditorDirty}
            />
          )}
        </div>
      </div>

      <AdviceCard injuryTypeId={injuryTypeId} />
    </div>
  );
}
