import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { AnswerValue, Question } from "../../api/types";

type Props = {
  question: Question;
  value: AnswerValue;
  onChange: (value: AnswerValue) => void;
  /** The builder preview renders this component without stealing focus. */
  autoFocus?: boolean;
};

function todayISO(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

type StateInfo = { code: string; name: string };
// Static reference data — cache for the life of the page.
let statesCache: StateInfo[] | null = null;
const countiesCache: Record<string, string[]> = {};

function UsStateCountyInput({
  value,
  onChange,
  autoFocus,
}: {
  value: AnswerValue;
  onChange: (value: AnswerValue) => void;
  autoFocus: boolean;
}) {
  const [stateCode, county] = Array.isArray(value) ? value : [];
  const [states, setStates] = useState<StateInfo[]>(statesCache ?? []);
  const [counties, setCounties] = useState<string[]>(
    stateCode ? (countiesCache[stateCode] ?? []) : [],
  );

  useEffect(() => {
    if (statesCache) return;
    api<StateInfo[]>("/geo/states")
      .then((list) => {
        statesCache = list;
        setStates(list);
      })
      .catch(() => setStates([]));
  }, []);

  useEffect(() => {
    if (!stateCode) {
      setCounties([]);
      return;
    }
    if (countiesCache[stateCode]) {
      setCounties(countiesCache[stateCode]);
      return;
    }
    let cancelled = false;
    api<string[]>(`/geo/counties/${stateCode}`)
      .then((list) => {
        countiesCache[stateCode] = list;
        if (!cancelled) setCounties(list);
      })
      .catch(() => {
        if (!cancelled) setCounties([]);
      });
    return () => {
      cancelled = true;
    };
  }, [stateCode]);

  return (
    <div className="state-county">
      <select
        className="select wizard-input"
        aria-label="State"
        value={stateCode ?? ""}
        onChange={(e) => onChange(e.target.value ? [e.target.value] : null)}
        autoFocus={autoFocus}
      >
        <option value="">Select a state…</option>
        {states.map((s) => (
          <option key={s.code} value={s.code}>
            {s.name}
          </option>
        ))}
      </select>
      <select
        className="select wizard-input"
        aria-label="County"
        value={county ?? ""}
        disabled={!stateCode}
        onChange={(e) =>
          onChange(e.target.value ? [stateCode!, e.target.value] : [stateCode!])
        }
      >
        <option value="">{stateCode ? "Select a county…" : "Pick a state first"}</option>
        {counties.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
    </div>
  );
}

export function QuestionRenderer({ question, value, onChange, autoFocus = true }: Props) {
  const config = question.config ?? {};
  const placeholder = config.placeholder ?? "";

  switch (question.type) {
    case "single_choice":
      // Long option lists (e.g. all 50 US states) render as a dropdown; a
      // button per option only works for a handful of choices.
      if (question.options.length > 8) {
        return (
          <select
            className="select wizard-input"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
            autoFocus={autoFocus}
          >
            <option value="">Select…</option>
            {question.options.map((opt) => (
              <option key={opt.id} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        );
      }
      return (
        <div className="choice-list">
          {question.options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`choice ${value === opt.value ? "selected" : ""}`}
              onClick={() => onChange(opt.value)}
            >
              <span className="choice-dot" />
              {opt.label}
            </button>
          ))}
        </div>
      );

    case "multi_choice": {
      const selected = Array.isArray(value) ? value : [];
      const toggle = (v: string) =>
        onChange(
          selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v],
        );
      return (
        <div className="choice-list">
          {question.options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={`choice ${selected.includes(opt.value) ? "selected" : ""}`}
              onClick={() => toggle(opt.value)}
            >
              <span className="choice-box" />
              {opt.label}
            </button>
          ))}
        </div>
      );
    }

    case "yes_no":
      return (
        <div className="choice-list yesno">
          {[
            ["Yes", true],
            ["No", false],
          ].map(([label, v]) => (
            <button
              key={String(label)}
              type="button"
              className={`choice ${value === v ? "selected" : ""}`}
              onClick={() => onChange(v as boolean)}
            >
              {label}
            </button>
          ))}
        </div>
      );

    case "long_text":
      return (
        <textarea
          className="textarea wizard-input"
          placeholder={placeholder}
          maxLength={config.max_length}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          autoFocus={autoFocus}
        />
      );

    case "number":
      return (
        <input
          className="input wizard-input"
          type="number"
          placeholder={placeholder}
          min={config.min}
          max={config.max}
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          autoFocus={autoFocus}
        />
      );

    case "date":
      return (
        <input
          className="input wizard-input"
          type="date"
          max={config.disallow_future ? todayISO() : undefined}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          autoFocus={autoFocus}
        />
      );

    case "us_state_county":
      return (
        <UsStateCountyInput value={value} onChange={onChange} autoFocus={autoFocus} />
      );

    case "short_text":
    default:
      return (
        <input
          className="input wizard-input"
          type="text"
          placeholder={placeholder}
          maxLength={config.max_length}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          autoFocus={autoFocus}
        />
      );
  }
}
