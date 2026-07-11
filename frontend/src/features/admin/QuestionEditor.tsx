import { useEffect, useState } from "react";

import type { Question, QuestionConfig, QuestionType } from "../../api/types";

export type QuestionDraft = {
  type: QuestionType;
  prompt: string;
  help_text: string | null;
  is_required: boolean;
  config: QuestionConfig;
  options: { label: string; value: string }[];
};

const TEXT_TYPES: QuestionType[] = ["short_text", "long_text"];

/** Drop config keys that don't apply to the new type so stale bounds never
 * ride along after a type switch. */
function pruneConfig(config: QuestionConfig, type: QuestionType): QuestionConfig {
  const pruned: QuestionConfig = {};
  if (config.placeholder && [...TEXT_TYPES, "number"].includes(type)) {
    pruned.placeholder = config.placeholder;
  }
  if (type === "number") {
    if (config.min !== undefined) pruned.min = config.min;
    if (config.max !== undefined) pruned.max = config.max;
  }
  if (TEXT_TYPES.includes(type) && config.max_length !== undefined) {
    pruned.max_length = config.max_length;
  }
  if (type === "date" && config.disallow_future) {
    pruned.disallow_future = true;
  }
  return pruned;
}

type Props = {
  initial: Question | null;
  saving: boolean;
  onSave: (draft: QuestionDraft) => void;
  onDelete?: () => void;
};

const TYPE_LABELS: Record<QuestionType, string> = {
  single_choice: "Single choice",
  multi_choice: "Multiple choice",
  short_text: "Short text",
  number: "Number",
  date: "Date",
  yes_no: "Yes / No",
  long_text: "Long text",
};

const CHOICE_TYPES: QuestionType[] = ["single_choice", "multi_choice"];

function emptyDraft(): QuestionDraft {
  return {
    type: "single_choice",
    prompt: "",
    help_text: null,
    is_required: true,
    config: {},
    options: [{ label: "", value: "" }],
  };
}

function slugifyValue(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

export function QuestionEditor({ initial, saving, onSave, onDelete }: Props) {
  const [draft, setDraft] = useState<QuestionDraft>(emptyDraft());

  useEffect(() => {
    if (initial) {
      setDraft({
        type: initial.type,
        prompt: initial.prompt,
        help_text: initial.help_text,
        is_required: initial.is_required,
        config: initial.config ?? {},
        options: initial.options.map((o) => ({ label: o.label, value: o.value })),
      });
    } else {
      setDraft(emptyDraft());
    }
  }, [initial]);

  const set = <K extends keyof QuestionDraft>(key: K, value: QuestionDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const setType = (type: QuestionType) =>
    setDraft((d) => ({ ...d, type, config: pruneConfig(d.config, type) }));

  const setConfig = <K extends keyof QuestionConfig>(
    key: K,
    value: QuestionConfig[K] | undefined,
  ) =>
    setDraft((d) => {
      const config = { ...d.config };
      if (value === undefined || value === "" || value === false) {
        delete config[key];
      } else {
        config[key] = value;
      }
      return { ...d, config };
    });

  const isChoice = CHOICE_TYPES.includes(draft.type);
  const showPlaceholder = ["short_text", "long_text", "number"].includes(draft.type);

  function handleSave() {
    const options = isChoice
      ? draft.options
          .filter((o) => o.label.trim())
          .map((o) => ({ label: o.label.trim(), value: o.value.trim() || slugifyValue(o.label) }))
      : [];
    onSave({ ...draft, options });
  }

  const canSave =
    draft.prompt.trim().length > 0 &&
    (!isChoice || draft.options.some((o) => o.label.trim()));

  return (
    <div className="editor">
      <h2>{initial ? "Edit question" : "New question"}</h2>

      <div className="field">
        <label>Type</label>
        <select
          className="select"
          value={draft.type}
          onChange={(e) => setType(e.target.value as QuestionType)}
        >
          {Object.entries(TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>Prompt</label>
        <input
          className="input"
          value={draft.prompt}
          onChange={(e) => set("prompt", e.target.value)}
          placeholder="e.g. Were you the driver or a passenger?"
        />
      </div>

      <div className="field">
        <label>Help text (optional)</label>
        <input
          className="input"
          value={draft.help_text ?? ""}
          onChange={(e) => set("help_text", e.target.value || null)}
        />
      </div>

      {showPlaceholder && (
        <div className="field">
          <label>Placeholder (optional)</label>
          <input
            className="input"
            value={draft.config.placeholder ?? ""}
            onChange={(e) => setConfig("placeholder", e.target.value || undefined)}
          />
        </div>
      )}

      {draft.type === "number" && (
        <div className="field-row">
          <div className="field">
            <label>Minimum (optional)</label>
            <input
              className="input"
              type="number"
              value={draft.config.min ?? ""}
              onChange={(e) =>
                setConfig("min", e.target.value === "" ? undefined : Number(e.target.value))
              }
            />
          </div>
          <div className="field">
            <label>Maximum (optional)</label>
            <input
              className="input"
              type="number"
              value={draft.config.max ?? ""}
              onChange={(e) =>
                setConfig("max", e.target.value === "" ? undefined : Number(e.target.value))
              }
            />
          </div>
        </div>
      )}

      {draft.type === "date" && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.config.disallow_future ?? false}
            onChange={(e) => setConfig("disallow_future", e.target.checked || undefined)}
          />
          Don&apos;t allow future dates
        </label>
      )}

      {TEXT_TYPES.includes(draft.type) && (
        <div className="field">
          <label>Max length (optional)</label>
          <input
            className="input"
            type="number"
            min={1}
            value={draft.config.max_length ?? ""}
            onChange={(e) =>
              setConfig(
                "max_length",
                e.target.value === "" ? undefined : Number(e.target.value),
              )
            }
          />
        </div>
      )}

      {isChoice && (
        <div className="field">
          <label>Options</label>
          {draft.options.map((opt, idx) => (
            <div key={idx} className="option-row">
              <input
                className="input"
                placeholder="Option label"
                value={opt.label}
                onChange={(e) => {
                  const options = [...draft.options];
                  options[idx] = { ...options[idx], label: e.target.value };
                  set("options", options);
                }}
              />
              <button
                className="btn btn-danger"
                type="button"
                onClick={() => set("options", draft.options.filter((_, i) => i !== idx))}
              >
                ✕
              </button>
            </div>
          ))}
          <button
            className="btn btn-outline"
            type="button"
            onClick={() => set("options", [...draft.options, { label: "", value: "" }])}
          >
            + Add option
          </button>
        </div>
      )}

      <label className="checkbox">
        <input
          type="checkbox"
          checked={draft.is_required}
          onChange={(e) => set("is_required", e.target.checked)}
        />
        Required
      </label>

      <div className="editor-actions">
        <button className="btn btn-primary" onClick={handleSave} disabled={!canSave || saving}>
          {initial ? "Save changes" : "Add question"}
        </button>
        {onDelete && initial && (
          <button
            className="btn btn-danger"
            onClick={() => {
              if (confirm("Delete this question?")) onDelete();
            }}
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}
