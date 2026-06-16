import type { AnswerValue, Question } from "../../api/types";

type Props = {
  question: Question;
  value: AnswerValue;
  onChange: (value: AnswerValue) => void;
};

export function QuestionRenderer({ question, value, onChange }: Props) {
  const placeholder = (question.config?.placeholder as string) ?? "";

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
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
        />
      );

    case "number":
      return (
        <input
          className="input wizard-input"
          type="number"
          placeholder={placeholder}
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          autoFocus
        />
      );

    case "date":
      return (
        <input
          className="input wizard-input"
          type="date"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
        />
      );

    case "short_text":
    default:
      return (
        <input
          className="input wizard-input"
          type="text"
          placeholder={placeholder}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
        />
      );
  }
}
