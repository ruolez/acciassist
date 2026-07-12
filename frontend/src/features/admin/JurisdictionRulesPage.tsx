import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ApiError } from "../../api/client";
import type { ComparativeRule, JurisdictionRule } from "../../api/types";
import "./admin.css";

const KEY = ["admin", "jurisdictions"];

const RULE_LABELS: Record<ComparativeRule, string> = {
  pure: "Pure comparative",
  modified_50: "Modified — barred at 50%",
  modified_51: "Modified — barred at 51%",
  contributory: "Contributory (any fault bars)",
};

type Draft = {
  comparative_rule: ComparativeRule;
  no_fault: boolean;
  pip_threshold_note: string;
  sol_years_pi: string;
  sol_note: string;
  noneconomic_cap: string;
  cap_note: string;
  collateral_source_note: string;
  needs_review: boolean;
};

function toDraft(rule: JurisdictionRule): Draft {
  return {
    comparative_rule: rule.comparative_rule,
    no_fault: rule.no_fault,
    pip_threshold_note: rule.pip_threshold_note ?? "",
    sol_years_pi: String(rule.sol_years_pi),
    sol_note: rule.sol_note ?? "",
    noneconomic_cap: rule.noneconomic_cap === null ? "" : String(rule.noneconomic_cap),
    cap_note: rule.cap_note ?? "",
    collateral_source_note: rule.collateral_source_note ?? "",
    needs_review: rule.needs_review,
  };
}

function toPayload(draft: Draft) {
  return {
    comparative_rule: draft.comparative_rule,
    no_fault: draft.no_fault,
    pip_threshold_note: draft.pip_threshold_note.trim() || null,
    sol_years_pi: Number(draft.sol_years_pi),
    sol_note: draft.sol_note.trim() || null,
    noneconomic_cap: draft.noneconomic_cap.trim() === "" ? null : Number(draft.noneconomic_cap),
    cap_note: draft.cap_note.trim() || null,
    collateral_source_note: draft.collateral_source_note.trim() || null,
    needs_review: draft.needs_review,
  };
}

const NOTE_FIELDS: { key: keyof Draft; label: string }[] = [
  { key: "pip_threshold_note", label: "PIP / tort-threshold note" },
  { key: "sol_note", label: "SOL note (tolling, exceptions)" },
  { key: "cap_note", label: "Damage-cap note" },
  { key: "collateral_source_note", label: "Collateral source note" },
];

function RuleEditor({ rule, onClose }: { rule: JurisdictionRule; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => toDraft(rule));
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      api<JurisdictionRule>(`/admin/jurisdictions/${rule.state_code}`, {
        method: "PUT",
        body: toPayload(draft),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: KEY });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not save"),
  });

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));
  const solValid = Number(draft.sol_years_pi) > 0 && Number(draft.sol_years_pi) <= 20;

  return (
    <div className="jurisdiction-editor">
      <div className="settings-grid">
        <div className="field">
          <label>Comparative negligence rule</label>
          <select
            className="select"
            value={draft.comparative_rule}
            onChange={(e) => set("comparative_rule", e.target.value as ComparativeRule)}
          >
            {Object.entries(RULE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Statute of limitations (years)</label>
          <input
            className="input"
            type="number"
            min={0.5}
            max={20}
            step={0.5}
            value={draft.sol_years_pi}
            onChange={(e) => set("sol_years_pi", e.target.value)}
          />
        </div>
        <div className="field">
          <label>Non-economic cap ($, blank = none)</label>
          <input
            className="input"
            type="number"
            min={0}
            value={draft.noneconomic_cap}
            onChange={(e) => set("noneconomic_cap", e.target.value)}
          />
        </div>
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={draft.no_fault}
          onChange={(e) => set("no_fault", e.target.checked)}
        />
        No-fault / PIP state
      </label>
      {NOTE_FIELDS.map(({ key, label }) => (
        <div className="field" key={key}>
          <label>{label}</label>
          <textarea
            className="input"
            rows={2}
            value={draft[key] as string}
            onChange={(e) => set(key, e.target.value as Draft[typeof key])}
          />
        </div>
      ))}
      <label className="checkbox">
        <input
          type="checkbox"
          checked={!draft.needs_review}
          onChange={(e) => set("needs_review", !e.target.checked)}
        />
        Verified by an attorney
      </label>
      {error && <p className="error-text">{error}</p>}
      <div className="editor-actions">
        <button
          className="btn btn-primary"
          disabled={!solValid || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button className="btn btn-ghost" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export function JurisdictionRulesPage() {
  const [openCode, setOpenCode] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: KEY,
    queryFn: () => api<JurisdictionRule[]>("/admin/jurisdictions"),
  });

  const unreviewed = data?.filter((r) => r.needs_review).length ?? 0;

  return (
    <div className="page">
      <div className="page-head">
        <h1>Jurisdiction Rules</h1>
      </div>
      <p className="muted">
        Per-state legal parameters used by the estimate pipeline: comparative-negligence rule,
        statute of limitations, no-fault thresholds, and damage caps.
      </p>
      {unreviewed > 0 && (
        <div className="card jurisdiction-warning">
          {unreviewed} of {data?.length} states are seeded from public sources and have not been
          verified by an attorney. Estimates in those states carry a verification disclaimer
          until each row is reviewed and marked verified.
        </div>
      )}

      {isLoading && <p className="muted">Loading…</p>}
      <div className="table-list">
        {data?.map((rule) => (
          <div key={rule.state_code} className="card jurisdiction-row">
            <div className="jurisdiction-summary">
              <span className="jurisdiction-state">
                <strong>{rule.state_code}</strong> {rule.state_name}
              </span>
              <span className="muted">{RULE_LABELS[rule.comparative_rule]}</span>
              <span className="muted">SOL {rule.sol_years_pi}y</span>
              {rule.no_fault && <span className="badge badge-on">no-fault</span>}
              {rule.noneconomic_cap !== null && (
                <span className="muted">cap ${rule.noneconomic_cap.toLocaleString()}</span>
              )}
              <span className={`badge ${rule.needs_review ? "badge-off" : "badge-on"}`}>
                {rule.needs_review ? "needs review" : "verified"}
              </span>
              <button
                className="btn btn-ghost"
                onClick={() =>
                  setOpenCode(openCode === rule.state_code ? null : rule.state_code)
                }
              >
                {openCode === rule.state_code ? "Close" : "Edit"}
              </button>
            </div>
            {openCode === rule.state_code && (
              <RuleEditor rule={rule} onClose={() => setOpenCode(null)} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
