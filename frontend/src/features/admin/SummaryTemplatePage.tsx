import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { Question, SummaryTemplate } from "../../api/types";
import { findUnknownTokens } from "./template-tokens";
import { useActionError } from "./useActionError";
import "./admin.css";

export function SummaryTemplatePage() {
  const { id } = useParams();
  const injuryTypeId = Number(id);
  const queryClient = useQueryClient();
  const key = ["admin", "summary-template", injuryTypeId];

  const { data } = useQuery({
    queryKey: key,
    queryFn: () =>
      api<SummaryTemplate>(`/admin/injury-types/${injuryTypeId}/summary-template`),
  });
  const { data: questions } = useQuery({
    queryKey: ["admin", "questions", injuryTypeId],
    queryFn: () => api<Question[]>(`/admin/injury-types/${injuryTypeId}/questions`),
  });

  const [body, setBody] = useState("");
  const [min, setMin] = useState<string>("");
  const [max, setMax] = useState<string>("");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const { error, onError, clear } = useActionError();
  const bodyRef = useRef<HTMLTextAreaElement | null>(null);

  const unknownTokens = questions
    ? findUnknownTokens(body, new Set(questions.map((q) => q.slug)))
    : [];

  const insertToken = (slug: string) => {
    const el = bodyRef.current;
    const token = `{{${slug}}}`;
    if (!el) {
      setBody((b) => b + token);
      return;
    }
    const start = el.selectionStart ?? body.length;
    const end = el.selectionEnd ?? body.length;
    setBody(body.slice(0, start) + token + body.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.selectionStart = el.selectionEnd = start + token.length;
    });
  };

  useEffect(() => {
    if (data) {
      setBody(data.body);
      setMin(data.estimate_min?.toString() ?? "");
      setMax(data.estimate_max?.toString() ?? "");
      setNote(data.estimate_note);
    }
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      api(`/admin/injury-types/${injuryTypeId}/summary-template`, {
        method: "PUT",
        body: {
          body,
          estimate_min: min === "" ? null : Number(min),
          estimate_max: max === "" ? null : Number(max),
          estimate_note: note,
        },
      }),
    onSuccess: () => {
      setSaved(true);
      clear();
      queryClient.invalidateQueries({ queryKey: key });
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (e) => onError(e, "Could not save the template"),
  });

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <Link className="back-link" to="/admin/injury-types">
            ← Injury Types
          </Link>
          <h1>Summary Template</h1>
        </div>
        <button className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>
          {saved ? "Saved ✓" : "Save"}
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}

      <div className="card editor">
        <div className="field">
          <label>Summary body</label>
          <textarea
            ref={bodyRef}
            className="textarea"
            style={{ minHeight: 240 }}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          {unknownTokens.length > 0 && (
            <p className="error-text">
              These tokens don&apos;t match any question and will render as blank text:{" "}
              {unknownTokens.map((t) => `{{${t}}}`).join(", ")}
            </p>
          )}
          <span className="help-text">
            Click a token to insert the patient&apos;s answer at the cursor:
          </span>
          <div className="token-list">
            {questions?.map((q) => (
              <button
                key={q.id}
                type="button"
                className="token token-button"
                title={q.prompt}
                onClick={() => insertToken(q.slug)}
              >{`{{${q.slug}}}`}</button>
            ))}
          </div>
        </div>

        <div className="field-row">
          <div className="field">
            <label>Estimate min ($)</label>
            <input
              className="input"
              type="number"
              value={min}
              onChange={(e) => setMin(e.target.value)}
            />
          </div>
          <div className="field">
            <label>Estimate max ($)</label>
            <input
              className="input"
              type="number"
              value={max}
              onChange={(e) => setMax(e.target.value)}
            />
          </div>
        </div>

        <div className="field">
          <label>Estimate note</label>
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
      </div>
    </div>
  );
}
