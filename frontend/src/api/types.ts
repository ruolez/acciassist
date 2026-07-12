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

export type QuestionConfig = {
  placeholder?: string;
  min?: number;
  max?: number;
  max_length?: number;
  disallow_future?: boolean;
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
  config: QuestionConfig;
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
  estimate: CaseEstimateAdmin | null;
};

export type PublicEstimate = {
  status: "none" | "pending" | "completed" | "failed";
  payout_min: number | null;
  payout_max: number | null;
};

export type CaseEstimateAdmin = {
  status: "pending" | "completed" | "failed";
  payout_min: number | null;
  payout_max: number | null;
  case_cost_min: number | null;
  case_cost_max: number | null;
  confidence: string | null;
  reasoning: string | null;
  missing_info: string[] | null;
  model: string | null;
  error: string | null;
  updated_at: string;
};

export type OpenRouterModel = {
  id: string;
  name: string;
  context_length: number | null;
  prompt_price: string | null;
  completion_price: string | null;
  supports_structured_outputs: boolean;
};

export type QuestionPayload = {
  type: QuestionType;
  prompt: string;
  help_text: string | null;
  is_required: boolean;
  config: QuestionConfig;
  options: { label: string; value: string }[];
};

export type ProposalAdd = {
  id: string;
  kind: "add";
  payload: QuestionPayload;
  rationale: string;
  applied: boolean;
  applied_at: string | null;
  created_question_id: number | null;
};

export type ProposalEdit = {
  id: string;
  kind: "edit";
  question_id: number;
  payload: QuestionPayload;
  rationale: string;
  change_summary: string;
  applied: boolean;
  applied_at: string | null;
};

export type Proposal = ProposalAdd | ProposalEdit;

export type EstimateAdvice = {
  content: string;
  proposals: Proposal[] | null;
  model: string | null;
  updated_at: string;
};

/** Answer value as held in the wizard before submission. */
export type AnswerValue = string | number | boolean | string[] | null;

export type User = {
  id: number;
  email: string;
  name: string;
  phone: string | null;
  created_at: string;
};

export type CaseStage =
  | "new"
  | "under_review"
  | "documents_needed"
  | "negotiating"
  | "settled"
  | "closed";

export type CaseUpdate = {
  id: number;
  kind: "message" | "stage_change";
  body: string;
  created_at: string;
};

export type CaseListItem = {
  id: number;
  stage: CaseStage;
  created_at: string;
  injury_type_name: string | null;
  estimate_min: number | null;
  estimate_max: number | null;
};

export type CaseDetail = CaseListItem & {
  updates: CaseUpdate[];
  summary: Summary | null;
  name: string;
  email: string;
  phone: string | null;
};

export type AdminCaseUpdate = CaseUpdate & { admin_email: string | null };

export type AdminCaseListItem = {
  id: number;
  stage: CaseStage;
  created_at: string;
  lead_name: string;
  lead_email: string;
  lead_phone: string | null;
  user_claimed: boolean;
  injury_type_name: string | null;
};

export type AdminCaseDetail = AdminCaseListItem & {
  intake_session_id: string | null;
  updates: AdminCaseUpdate[];
  estimate: CaseEstimateAdmin | null;
};

export type AppSettings = {
  smtp_host: string | null;
  smtp_port: number;
  smtp_username: string | null;
  smtp_password_set: boolean;
  smtp_tls_mode: "none" | "starttls" | "ssl";
  from_email: string | null;
  from_name: string;
  app_base_url: string | null;
  openrouter_api_key_set: boolean;
  openrouter_model: string | null;
};

export type ComparativeRule = "pure" | "modified_50" | "modified_51" | "contributory";

export type JurisdictionRule = {
  state_code: string;
  state_name: string;
  comparative_rule: ComparativeRule;
  no_fault: boolean;
  pip_threshold_note: string | null;
  sol_years_pi: number;
  sol_note: string | null;
  noneconomic_cap: number | null;
  cap_note: string | null;
  collateral_source_note: string | null;
  needs_review: boolean;
  updated_at: string;
};

export type EmailLogEntry = {
  id: number;
  to_email: string;
  subject: string;
  purpose: string;
  status: "sent" | "failed" | "skipped";
  error: string | null;
  case_id: number | null;
  created_at: string;
};
