import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { CaseEstimateAdmin, StageStatus } from "../../api/types";
import "./admin.css";

const STAGES = ["extraction", "gates", "comps", "judgment", "adversarial", "assembly"];

export function formatUsdRange(min: number | null, max: number | null): string {
  if (min === null && max === null) return "—";
  const fmt = (n: number) => `$${n.toLocaleString()}`;
  if (min !== null && max !== null) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max)!);
}

function StageChips({ stages }: { stages: Record<string, StageStatus> }) {
  return (
    <div className="stage-chips">
      {STAGES.map((name) => {
        const s = stages[name];
        if (!s) return null;
        return (
          <span
            key={name}
            className={`stage-chip stage-${s.status}`}
            title={s.error ?? (s.ms !== undefined ? `${s.ms} ms` : undefined)}
          >
            {name}
            {s.status === "failed" && " ✕"}
            {s.status === "skipped" && " —"}
            {s.status === "completed" && " ✓"}
          </span>
        );
      })}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="pipeline-section">
      <summary>{title}</summary>
      <div className="pipeline-section-body">{children}</div>
    </details>
  );
}

function CompletedDetail({ data }: { data: CaseEstimateAdmin }) {
  const result = data.result;
  const internals = data.internals;
  const samples = internals?.samples;

  return (
    <>
      {result?.gated && (
        <div className="jurisdiction-warning">
          <strong>Gated — {result.gated.title}</strong>
          <p>{result.gated.explanation}</p>
        </div>
      )}
      <div className="estimate-admin-grid">
        <div>
          <span className="muted">Gross settlement</span>
          <p className="estimate-admin-figure">
            {formatUsdRange(data.gross_min ?? data.payout_min, data.gross_max ?? data.payout_max)}
          </p>
        </div>
        <div>
          <span className="muted">Net to client</span>
          <p className="estimate-admin-figure">{formatUsdRange(data.net_min, data.net_max)}</p>
        </div>
        <div>
          <span className="muted">Case cost</span>
          <p className="estimate-admin-figure">
            {formatUsdRange(data.case_cost_min, data.case_cost_max)}
          </p>
        </div>
        <div>
          <span className="muted">Confidence</span>
          <p>
            <span className={`badge confidence-${data.confidence ?? "low"}`}>
              {data.confidence ?? "—"}
            </span>
            {result?.width != null && (
              <span className="muted"> ±{Math.round(result.width * 100)}%</span>
            )}
          </p>
        </div>
      </div>
      {data.reasoning && <p className="estimate-admin-reasoning">{data.reasoning}</p>}

      {result && !result.gated && (
        <Section title="Patient view">
          {result.drivers.length > 0 && (
            <>
              <span className="muted">What strengthens the case</span>
              <ul>
                {result.drivers.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </>
          )}
          {result.reducers.length > 0 && (
            <>
              <span className="muted">What could reduce it</span>
              <ul>
                {result.reducers.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </>
          )}
          {result.improvements.length > 0 && (
            <>
              <span className="muted">Documentation that would improve it</span>
              <ul>
                {result.improvements.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </>
          )}
          {result.warnings.length > 0 && (
            <>
              <span className="muted">Warnings</span>
              <ul>
                {result.warnings.map((w) => (
                  <li key={w.code}>
                    <strong>{w.severity === "time_critical" ? "⚠ " : ""}</strong>
                    {w.message}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      )}

      {samples && samples.valid.length > 0 && (
        <Section
          title={`Judgment samples (${samples.valid.length}/${samples.requested} · median tier ${samples.median_tier ?? "—"} · liability ${samples.median_liability_pct ?? "—"}%)`}
        >
          <table className="samples-table">
            <thead>
              <tr>
                <th>Tier</th>
                <th>Liability %</th>
                <th>Swing fact</th>
              </tr>
            </thead>
            <tbody>
              {samples.valid.map((s, i) => (
                <tr key={i}>
                  <td>{s.severity_tier}</td>
                  <td>{s.defendant_liability_pct}</td>
                  <td>{s.swing_fact}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            Spread: tier ±{samples.tier_spread ?? 0}, liability ±{samples.liability_spread ?? 0}%
            {samples.errors.length > 0 && ` · ${samples.errors.length} failed sample(s)`}
          </p>
        </Section>
      )}

      {internals?.comps && internals.comps.comps.length > 0 && (
        <Section title={`Comparable results (${internals.comps.comps.length} · ${internals.comps.model})`}>
          <ul>
            {internals.comps.comps.map((c, i) => (
              <li key={i}>
                ${c.amount.toLocaleString()} — {c.description} ({c.venue}
                {c.year ? `, ${c.year}` : ""}){" "}
                <span className={`badge comp-${c.source_quality}`}>{c.source_quality}</span>{" "}
                {c.source_url && (
                  <a href={c.source_url} target="_blank" rel="noreferrer">
                    source
                  </a>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {internals?.adversarial && (
        <Section
          title={`Defense adjuster (floor: ${internals.adversarial.lowest_defensible_pct_of_specials}% of specials)`}
        >
          {internals.adversarial.low_rationale && (
            <p>{internals.adversarial.low_rationale}</p>
          )}
          <ul>
            {internals.adversarial.attack_arguments.map((a, i) => (
              <li key={i}>
                <strong>{a.category}:</strong> {a.argument}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {internals?.assembly_trace && (
        <Section title="Assembly trace">
          <pre className="pipeline-json">
            {JSON.stringify(internals.assembly_trace, null, 2)}
          </pre>
        </Section>
      )}

      {internals?.extraction && (
        <Section title="Extraction">
          <pre className="pipeline-json">{JSON.stringify(internals.extraction, null, 2)}</pre>
        </Section>
      )}
    </>
  );
}

export function PipelineEstimateCard({
  sessionId,
  initial,
  onError,
}: {
  sessionId: string;
  initial: CaseEstimateAdmin | null;
  onError: (e: unknown, fallback: string) => void;
}) {
  const queryClient = useQueryClient();
  const KEY = ["admin", "ai", "estimate", sessionId];
  const { data } = useQuery({
    queryKey: KEY,
    queryFn: () => api<CaseEstimateAdmin | null>(`/admin/ai/sessions/${sessionId}/estimate`),
    initialData: initial,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 2000 : false),
  });

  const rerun = useMutation({
    mutationFn: () =>
      api<CaseEstimateAdmin>(`/admin/ai/sessions/${sessionId}/estimate/rerun`, {
        method: "POST",
      }),
    onSuccess: (pending) => queryClient.setQueryData(KEY, pending),
    onError: (e) => onError(e, "Could not re-run the estimate"),
  });

  return (
    <div className="card estimate-admin">
      <div className="estimate-admin-head">
        <h2>Estimate pipeline</h2>
        <button
          className="btn btn-outline"
          disabled={rerun.isPending || data?.status === "pending"}
          onClick={() => rerun.mutate()}
        >
          {data?.status === "pending" ? "Running…" : "Re-run estimate"}
        </button>
      </div>
      {data?.stage_status && <StageChips stages={data.stage_status} />}
      {!data && <p className="muted">No estimate yet — re-run to generate one.</p>}
      {data?.status === "pending" && <p className="muted">Running the pipeline…</p>}
      {data?.status === "failed" && (
        <p className="error-text">Estimate failed: {data.error ?? "unknown error"}</p>
      )}
      {data?.status === "completed" && <CompletedDetail data={data} />}
      {data && (
        <p className="muted estimate-admin-meta">
          {data.model} · {new Date(data.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
}
