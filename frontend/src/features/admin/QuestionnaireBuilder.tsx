import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { Question } from "../../api/types";
import { QuestionEditor, type QuestionDraft } from "./QuestionEditor";
import { SortableList } from "./SortableList";
import "./admin.css";

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
      invalidate();
    },
  });

  const update = useMutation({
    mutationFn: ({ qid, draft }: { qid: number; draft: QuestionDraft }) =>
      api(`/admin/injury-types/${injuryTypeId}/questions/${qid}`, {
        method: "PUT",
        body: draft,
      }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (qid: number) =>
      api(`/admin/injury-types/${injuryTypeId}/questions/${qid}`, { method: "DELETE" }),
    onSuccess: () => {
      setSelected(null);
      invalidate();
    },
  });

  const reorder = useMutation({
    mutationFn: (orderedIds: number[]) =>
      api(`/admin/injury-types/${injuryTypeId}/questions/reorder`, {
        method: "POST",
        body: { ordered_ids: orderedIds },
      }),
    onSuccess: invalidate,
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

      <div className="builder">
        <div className="builder-list card">
          <div className="builder-list-head">
            <span>Questions</span>
            <button className="btn btn-outline" onClick={() => setSelected("new")}>
              + Add
            </button>
          </div>
          {questions && questions.length === 0 && (
            <p className="muted builder-empty">No questions yet. Click “+ Add”.</p>
          )}
          {questions && (
            <SortableList
              items={questions}
              onReorder={(ids) => reorder.mutate(ids)}
              renderItem={(q) => (
                <button
                  className={`q-item ${selected === q.id ? "active" : ""}`}
                  onClick={() => setSelected(q.id)}
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
            />
          )}
        </div>
      </div>
    </div>
  );
}
