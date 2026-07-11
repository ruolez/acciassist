import type { AnswerValue, Question } from "../../api/types";

/** True when a value counts as a real answer for its question type. */
export function isAnswered(question: Question, value: AnswerValue): boolean {
  if (question.type === "multi_choice") {
    return Array.isArray(value) && value.length > 0;
  }
  if (question.type === "yes_no") {
    return typeof value === "boolean";
  }
  if (question.type === "number") {
    return typeof value === "number" && !Number.isNaN(value);
  }
  return typeof value === "string" && value.trim().length > 0;
}

/** Message when an answered value violates the question's configured bounds;
 * null when in range or not yet answered. */
export function boundsError(question: Question, value: AnswerValue): string | null {
  if (!isAnswered(question, value)) return null;
  const config = question.config ?? {};
  if (question.type === "number" && typeof value === "number") {
    if (config.min !== undefined && value < config.min) {
      return `Enter a number of at least ${config.min}`;
    }
    if (config.max !== undefined && value > config.max) {
      return `Enter a number no higher than ${config.max}`;
    }
  }
  if (question.type === "date" && config.disallow_future && typeof value === "string") {
    const today = new Date();
    today.setHours(23, 59, 59, 999);
    if (new Date(`${value}T00:00:00`) > today) {
      return "This date can't be in the future";
    }
  }
  if (
    (question.type === "short_text" || question.type === "long_text") &&
    typeof value === "string" &&
    config.max_length !== undefined &&
    value.length > config.max_length
  ) {
    return `Keep it under ${config.max_length} characters`;
  }
  return null;
}

/** A page may advance only when every required question on it is answered and
 * no answer (required or optional) violates its configured bounds. */
export function isPageComplete(
  questions: Question[],
  answers: Record<number, AnswerValue>,
): boolean {
  return questions.every((q) => {
    const value = answers[q.id] ?? null;
    if (q.is_required && !isAnswered(q, value)) return false;
    return boundsError(q, value) === null;
  });
}

/** Progress as a 0–100 percentage for the progress bar. */
export function progressPercent(pageIndex: number, totalPages: number): number {
  if (totalPages <= 0) return 0;
  return Math.round((pageIndex / totalPages) * 100);
}
