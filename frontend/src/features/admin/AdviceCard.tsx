import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../../api/client";
import type {
  EstimateAdvice,
  Proposal,
  ProposalAdd,
  ProposalEdit,
  Question,
  QuestionConfig,
  QuestionPayload,
} from "../../api/types";
import { TYPE_SHORT } from "./question-labels";

function configSummary(config: QuestionConfig): string | null {
  const parts: string[] = [];
  if (config.min !== undefined) parts.push(`min ${config.min}`);
  if (config.max !== undefined) parts.push(`max ${config.max}`);
  if (config.max_length !== undefined) parts.push(`max length ${config.max_length}`);
  if (config.placeholder) parts.push(`placeholder “${config.placeholder}”`);
  if (config.disallow_future) parts.push("no future dates");
  return parts.length ? parts.join(" · ") : null;
}

function PayloadDetail({ payload }: { payload: QuestionPayload }) {
  const config = configSummary(payload.config);
  return (
    <>
      <p className="proposal-prompt">
        <span className="badge proposal-badge">{TYPE_SHORT[payload.type]}</span>
        {payload.prompt}
        <span className="muted proposal-required">
          {payload.is_required ? "· required" : "· optional"}
        </span>
      </p>
      {payload.help_text && <p className="muted proposal-help">{payload.help_text}</p>}
      {payload.options.length > 0 && (
        <div className="proposal-options">
          {payload.options.map((o) => (
            <span key={o.value} className="proposal-option-chip">
              {o.label}
            </span>
          ))}
        </div>
      )}
      {config && <p className="muted proposal-config">{config}</p>}
    </>
  );
}

export function AdviceCard({
  injuryTypeId,
  questions,
  title = "AI recommendations",
  description = "Ask the AI what this questionnaire should collect for accurate case cost and payout estimates. It proposes ready-to-add questions and improvements you can review and apply.",
  generatePath,
  generateLabel = "Ask AI what's needed",
}: {
  injuryTypeId: number;
  questions: Question[] | undefined;
  title?: string;
  description?: string;
  /** Override for the generate endpoint (default: the injury-type advice endpoint). */
  generatePath?: string;
  generateLabel?: string;
}) {
  const queryClient = useQueryClient();
  const KEY = ["admin", "ai", "advice", injuryTypeId];
  const [adviceError, setAdviceError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data } = useQuery({
    queryKey: KEY,
    queryFn: () => api<EstimateAdvice | null>(`/admin/ai/injury-types/${injuryTypeId}/advice`),
  });

  const refreshFromServer = (advice: EstimateAdvice) => {
    setAdviceError(null);
    queryClient.setQueryData(KEY, advice);
    setSelected(new Set());
  };

  const failMessage = (e: unknown, fallback: string) =>
    e instanceof ApiError && e.code === "ai_not_configured"
      ? "Configure the OpenRouter key and model in Settings first."
      : e instanceof ApiError
        ? e.message
        : fallback;

  const generate = useMutation({
    mutationFn: () =>
      api<EstimateAdvice>(generatePath ?? `/admin/ai/injury-types/${injuryTypeId}/advice`, {
        method: "POST",
      }),
    onSuccess: refreshFromServer,
    onError: (e) => setAdviceError(failMessage(e, "Could not get AI recommendations")),
  });

  const apply = useMutation({
    mutationFn: (ids: string[]) =>
      api<EstimateAdvice>(`/admin/ai/injury-types/${injuryTypeId}/advice/apply`, {
        method: "POST",
        body: { proposal_ids: ids },
      }),
    onSuccess: (advice) => {
      refreshFromServer(advice);
      queryClient.invalidateQueries({ queryKey: ["admin", "questions", injuryTypeId] });
    },
    onError: (e) => {
      setAdviceError(failMessage(e, "Could not apply the selected proposals"));
      if (e instanceof ApiError && e.code === "stale_proposal") {
        queryClient.invalidateQueries({ queryKey: KEY });
        queryClient.invalidateQueries({ queryKey: ["admin", "questions", injuryTypeId] });
      }
    },
  });

  const proposals: Proposal[] = data?.proposals ?? [];
  const adds = proposals.filter((p): p is ProposalAdd => p.kind === "add");
  const edits = proposals.filter((p): p is ProposalEdit => p.kind === "edit");
  const questionById = new Map((questions ?? []).map((q) => [q.id, q]));

  const isStale = (p: ProposalEdit) =>
    questions !== undefined && !p.applied && !questionById.has(p.question_id);
  const removesOptions = (p: ProposalEdit) => {
    const target = questionById.get(p.question_id);
    if (!target) return false;
    return target.options.some((o) => !p.payload.options.some((n) => n.value === o.value));
  };

  const selectableIds = [
    ...adds.filter((p) => !p.applied).map((p) => p.id),
    ...edits.filter((p) => !p.applied && !isStale(p)).map((p) => p.id),
  ];

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleSection = (ids: string[]) =>
    setSelected((prev) => {
      const allOn = ids.length > 0 && ids.every((id) => prev.has(id));
      const next = new Set(prev);
      ids.forEach((id) => (allOn ? next.delete(id) : next.add(id)));
      return next;
    });

  const handleGenerate = () => {
    const hasUnapplied = proposals.some((p) => !p.applied);
    if (
      hasUnapplied &&
      !confirm("Regenerate recommendations? Proposals you haven't applied will be replaced.")
    ) {
      return;
    }
    setAdviceError(null);
    generate.mutate();
  };

  const sectionHeader = (title: string, ids: string[]) => (
    <div className="proposal-section-head">
      <h3>{title}</h3>
      {ids.length > 0 && (
        <button type="button" className="btn-link" onClick={() => toggleSection(ids)}>
          {ids.every((id) => selected.has(id)) ? "Deselect all" : "Select all"}
        </button>
      )}
    </div>
  );

  return (
    <div className="card advice-card">
      <div className="advice-head">
        <div>
          <h2>{title}</h2>
          <p className="muted">{description}</p>
        </div>
        <button
          className="btn btn-outline"
          disabled={generate.isPending}
          onClick={handleGenerate}
        >
          {generate.isPending
            ? "Asking…"
            : data && !generatePath
              ? "Regenerate"
              : generateLabel}
        </button>
      </div>
      {adviceError && <p className="error-text">{adviceError}</p>}

      {data && data.content && <p className="advice-overview">{data.content}</p>}

      {adds.length > 0 && (
        <div className="proposal-section">
          {sectionHeader(
            "Proposed new questions",
            adds.filter((p) => !p.applied).map((p) => p.id),
          )}
          {adds.map((p) => (
            <label
              key={p.id}
              className={`proposal-item${p.applied ? " applied" : ""}`}
            >
              <input
                type="checkbox"
                checked={p.applied || selected.has(p.id)}
                disabled={p.applied || apply.isPending}
                onChange={() => toggle(p.id)}
              />
              <div className="proposal-body">
                <PayloadDetail payload={p.payload} />
                {p.rationale && <p className="muted proposal-rationale">{p.rationale}</p>}
                {p.applied && <span className="badge proposal-applied">Added ✓</span>}
              </div>
            </label>
          ))}
        </div>
      )}

      {edits.length > 0 && (
        <div className="proposal-section">
          {sectionHeader(
            "Suggested edits to existing questions",
            edits.filter((p) => !p.applied && !isStale(p)).map((p) => p.id),
          )}
          {edits.map((p) => {
            const target = questionById.get(p.question_id);
            const stale = isStale(p);
            return (
              <label
                key={p.id}
                className={`proposal-item${p.applied ? " applied" : ""}${stale ? " stale" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={p.applied || selected.has(p.id)}
                  disabled={p.applied || stale || apply.isPending}
                  onChange={() => toggle(p.id)}
                />
                <div className="proposal-body">
                  <p className="proposal-prompt">
                    {stale ? (
                      <span className="muted">(question deleted)</span>
                    ) : (
                      (target?.prompt ?? `Question #${p.question_id}`)
                    )}
                  </p>
                  <p className="proposal-summary">{p.change_summary}</p>
                  {p.rationale && <p className="muted proposal-rationale">{p.rationale}</p>}
                  {removesOptions(p) && (
                    <span className="badge proposal-caution">
                      Removes existing answer options
                    </span>
                  )}
                  {!stale && target && (
                    <details className="proposal-diff">
                      <summary>Before / after</summary>
                      <div className="proposal-diff-cols">
                        <div>
                          <span className="muted">Current</span>
                          <PayloadDetail
                            payload={{
                              type: target.type,
                              prompt: target.prompt,
                              help_text: target.help_text,
                              is_required: target.is_required,
                              config: target.config,
                              options: target.options.map((o) => ({
                                label: o.label,
                                value: o.value,
                              })),
                            }}
                          />
                        </div>
                        <div>
                          <span className="muted">Proposed</span>
                          <PayloadDetail payload={p.payload} />
                        </div>
                      </div>
                    </details>
                  )}
                  {p.applied && <span className="badge proposal-applied">Updated ✓</span>}
                </div>
              </label>
            );
          })}
        </div>
      )}

      {proposals.length > 0 && selectableIds.length > 0 && (
        <button
          className="btn btn-primary"
          disabled={selected.size === 0 || apply.isPending}
          onClick={() => apply.mutate([...selected])}
        >
          {apply.isPending ? "Applying…" : `Apply selected (${selected.size})`}
        </button>
      )}

      {data && (
        <p className="muted advice-meta">
          {data.model} · {new Date(data.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}
