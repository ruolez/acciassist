export type QuestionType =
  | "single_choice"
  | "multi_choice"
  | "short_text"
  | "number"
  | "date"
  | "yes_no"
  | "long_text";

export type QuestionOption = {
  id: number;
  label: string;
  value: string;
  display_order: number;
};

export type Question = {
  id: number;
  slug: string;
  type: QuestionType;
  prompt: string;
  help_text: string | null;
  is_required: boolean;
  display_order: number;
  page_group: number | null;
  config: Record<string, unknown>;
  options: QuestionOption[];
};

export type InjuryType = {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  display_order: number;
  is_published: boolean;
};

export type IntakePage = {
  page_index: number;
  questions: Question[];
};

export type IntakeStart = {
  session_id: string;
  injury_type: InjuryType;
  pages: IntakePage[];
  total_pages: number;
};

export type Summary = {
  body: string;
  estimate_min: number | null;
  estimate_max: number | null;
  estimate_note: string;
};

export type SummaryTemplate = {
  id: number;
  body: string;
  estimate_min: number | null;
  estimate_max: number | null;
  estimate_note: string;
};

export type Admin = {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
};

export type Lead = {
  id: number;
  intake_session_id: string | null;
  name: string;
  email: string;
  phone: string | null;
  created_at: string;
};

export type IntakeSessionSummary = {
  id: string;
  injury_type_id: number;
  status: "in_progress" | "completed";
  started_at: string;
  completed_at: string | null;
};

export type IntakeSessionDetail = IntakeSessionSummary & {
  answers: { question_id: number; value: unknown }[];
};

/** Answer value as held in the wizard before submission. */
export type AnswerValue = string | number | boolean | string[] | null;
