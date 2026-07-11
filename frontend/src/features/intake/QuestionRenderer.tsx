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

export function QuestionRenderer({ question, value, onChange, autoFocus = true }: Props) {
  const config = question.config ?? {};
  const placeholder = config.placeholder ?? "";

  switch (question.type) {
    case "single_choice":
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
