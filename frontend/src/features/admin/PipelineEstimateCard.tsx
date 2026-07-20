import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { CaseEstimateAdmin, EstimateWarning, StageStatus } from "../../api/types";
import { buildReceipt, confidenceLabel } from "./estimate-receipt";
import "./admin.css";

/** Pipeline stages in run order, with plain-language labels. */
const PIPELINE_STEPS = [
  { key: "extraction", label: "Reading the intake answers" },
  { key: "gates", label: "Checking state legal rules" },
  { key: "comps", label: "Finding comparable cases" },
  { key: "judgment", label: "Scoring severity and fault" },
  { key: "adversarial", label: "Stress-testing against a defense adjuster" },
  { key: "assembly", label: "Calculating the range" },
];

export function formatUsdRange(min: number | null, max: number | null): string {
  if (min === null && max === null) return "—";
  const fmt = (n: number) => `$${n.toLocaleString()}`;
  if (min !== null && max !== null) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max)!);
}

function ProgressSteps({ stages }: { stages: Record<string, StageStatus> | null }) {
  let currentSeen = false;
  return (
    <ol className="pipeline-steps">
      {PIPELINE_STEPS.map(({ key, label }) => {
        const status = stages?.[key]?.status;
        if (status === "skipped") return null;
        let state: "done" | "current" | "waiting" = "waiting";
        if (status === "completed" || status === "failed") {
          state = "done";
        } else if (!currentSeen) {
          state = "current";
          currentSeen = true;
        }
        return (
          <li key={key} className={`pipeline-step ${state}`}>
            <span className="pipeline-step-mark" aria-hidden="true">
              {state === "done" ? "✓" : ""}
            </span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

function WarningsBanner({ warnings }: { warnings: EstimateWarning[] | undefined }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div className="admin-warnings">
      {warnings.map((w) => (
        <p
          key={w.code}
          className={`admin-warning ${w.severity === "time_critical" ? "urgent" : ""}`}
        >
          {w.severity === "time_critical" ? "⚠ " : ""}
          {w.message}
        </p>
      ))}
    </div>
  );
}

function FactorColumns({
  drivers,
  reducers,
}: {
  drivers: string[];
  reducers: string[];
}) {
  if (drivers.length === 0 && reducers.length === 0) return null;
  return (
    <div className="factor-cols">
      {drivers.length > 0 && (
        <div className="factor-col">
          <h3 className="factor-title up">What helps this case</h3>
          <ul>
            {drivers.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
      )}
      {reducers.length > 0 && (
        <div className="factor-col">
          <h3 className="factor-title down">What could reduce it</h3>
          <ul>
            {reducers.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StageChips({ stages }: { stages: Record<string, StageStatus> }) {
  return (
    <div className="stage-chips">
      {PIPELINE_STEPS.map(({ key }) => {
        const s = stages[key];
        if (!s) return null;
        return (
          <span
            key={key}
            className={`stage-chip stage-${s.status}`}
            title={s.error ?? (s.ms !== undefined ? `${s.ms} ms` : undefined)}
          >
            {key}
            {s.status === "failed" && " ✕"}
            {s.status === "skipped" && " —"}
            {s.status === "completed" && " ✓"}
          </span>
        );
      })}
    </div>
  );
}

function TechnicalDrawer({ data }: { data: CaseEstimateAdmin }) {
  const internals = data.internals;
  const samples = internals?.samples;
  return (
    <details className="pipeline-section technical-drawer">
      <summary>Technical details</summary>
      <div className="pipeline-section-body technical-body">
        {data.error && <p className="error-text">Error: {data.error}</p>}
        {data.stage_status && <StageChips stages={data.stage_status} />}

        {samples && samples.valid.length > 0 && (
          <div className="technical-block">
            <h4>
              Judgment samples ({samples.valid.length}/{samples.requested} · median tier{" "}
              {samples.median_tier ?? "—"} · liability {samples.median_liability_pct ?? "—"}%)
            </h4>
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
              Spread: tier ±{samples.tier_spread ?? 0}, liability ±
              {samples.liability_spread ?? 0}%
              {samples.errors.length > 0 && ` · ${samples.errors.length} failed sample(s)`}
            </p>
          </div>
        )}

        {internals?.comps && internals.comps.comps.length > 0 && (
          <div className="technical-block">
            <h4>
              Comparable results ({internals.comps.comps.length} · {internals.comps.model})
            </h4>
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
          </div>
        )}

        {internals?.adversarial && (
          <div className="technical-block">
            <h4>
              Defense adjuster (floor:{" "}
              {internals.adversarial.lowest_defensible_pct_of_specials}% of specials)
            </h4>
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
          </div>
        )}

        {internals?.assembly_trace && (
          <div className="technical-block">
            <h4>Assembly trace</h4>
            <pre className="pipeline-json">
              {JSON.stringify(internals.assembly_trace, null, 2)}
            </pre>
          </div>
        )}

        {internals?.extraction && (
          <div className="technical-block">
            <h4>Extraction</h4>
            <pre className="pipeline-json">
              {JSON.stringify(internals.extraction, null, 2)}
            </pre>
          </div>
        )}

        <p className="muted estimate-admin-meta">
          {data.model} · {new Date(data.updated_at).toLocaleString()}
        </p>
      </div>
    </details>
  );
}

function CompletedDetail({ data }: { data: CaseEstimateAdmin }) {
  const result = data.result;
  const receipt = buildReceipt(data);

  if (result?.gated) {
    return (
      <>
        <div className="jurisdiction-warning">
          <strong>No dollar estimate — {result.gated.title}</strong>
          <p>{result.gated.explanation}</p>
        </div>
        <WarningsBanner warnings={result.warnings} />
        <TechnicalDrawer data={data} />
      </>
    );
  }

  return (
    <>
      <WarningsBanner warnings={result?.warnings} />
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
              {confidenceLabel(data.confidence, result?.width)}
            </span>
          </p>
        </div>
      </div>

      {receipt.length > 0 && (
        <div className="receipt">
          <h3 className="receipt-title">How we got this number</h3>
          {receipt.map((row) => (
            <div key={row.id} className={`receipt-row ${row.kind}`}>
              <div className="receipt-main">
                <span className="receipt-label">{row.label}</span>
                <span className="receipt-amount">{row.amount}</span>
              </div>
              {row.detail && <p className="receipt-detail">{row.detail}</p>}
            </div>
          ))}
        </div>
      )}

      <FactorColumns drivers={result?.drivers ?? []} reducers={result?.reducers ?? []} />

      {result && (result.improvements.length > 0 || result.disclaimer) && (
        <details className="pipeline-section">
          <summary>What the patient sees</summary>
          <div className="pipeline-section-body">
            {result.improvements.length > 0 && (
              <>
                <span className="muted">Documentation that would improve the estimate</span>
                <ul>
                  {result.improvements.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              </>
            )}
            {result.disclaimer && <p className="muted">{result.disclaimer}</p>}
          </div>
        </details>
      )}

      <TechnicalDrawer data={data} />
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
        <h2>Case value estimate</h2>
        <button
          className="btn btn-outline"
          disabled={rerun.isPending || data?.status === "pending"}
          onClick={() => rerun.mutate()}
        >
          {data?.status === "pending" ? "Running…" : "Re-run estimate"}
        </button>
      </div>
      {!data && <p className="muted">No estimate yet — re-run to generate one.</p>}
      {data?.status === "pending" && <ProgressSteps stages={data.stage_status} />}
      {data?.status === "failed" && (
        <>
          <p className="estimate-failed">
            This estimate couldn&apos;t be completed. Re-running usually resolves it; the
            exact cause is under Technical details.
          </p>
          <TechnicalDrawer data={data} />
        </>
      )}
      {data?.status === "completed" && <CompletedDetail data={data} />}
    </div>
  );
}
