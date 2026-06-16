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

/** A page may advance only when every required question on it is answered. */
export function isPageComplete(
  questions: Question[],
  answers: Record<number, AnswerValue>,
): boolean {
  return questions.every(
    (q) => !q.is_required || isAnswered(q, answers[q.id] ?? null),
  );
}

/** Progress as a 0–100 percentage for the progress bar. */
export function progressPercent(pageIndex: number, totalPages: number): number {
  if (totalPages <= 0) return 0;
  return Math.round((pageIndex / totalPages) * 100);
}
