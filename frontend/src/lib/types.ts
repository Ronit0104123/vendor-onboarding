export type VendorStatus =
  | "INVITED" | "SUBMITTED" | "PROCESSING" | "PENDING_VENDOR" | "PENDING_INTERNAL"
  | "APPROVED" | "REJECTED" | "AUTO_CLOSED";
export type Severity = "PASS" | "WARN" | "FIXABLE" | "BLOCKING" | "NEEDS_REVIEW";
export type StageStatus = "pending" | "running" | "pass" | "warn" | "fail" | "review";

export interface Me {
  id: number; email: string; name: string; role: "ADMIN" | "VIEWER";
  csrf_token: string; buyer_name: string; four_eyes: boolean;
}

export interface VendorRow {
  id: number; ref: string; display_name: string; category: string; contact_email: string;
  requested_by: string; status: VendorStatus; attempt_count: number; max_attempts: number;
  created_at: string; updated_at: string; decided_at: string | null; reminder_due: boolean; days_waiting: number;
}

export interface Stats {
  total: number; by_status: Record<VendorStatus, number>; avg_hours_to_decision: number | null;
  decided: number; reminders_due: number; overrides_waiting: number; clock_offset_days: number;
}

export interface Stage {
  stage: string; name: string; status: StageStatus; started_at: string | null; duration_ms: number | null;
  input: Record<string, unknown> | null; output: Record<string, unknown> | null;
}

export interface CheckItem {
  stage: string; code: string; severity: Severity; reason: string; field: string | null; vendor_message: string | null;
}

export interface LlmCall {
  purpose: string; model: string; prompt_summary: string; ok: boolean; error: string | null; attempts: number;
  latency_ms: number; tokens_in: number; tokens_out: number; output: unknown; at: string;
}

export interface RunDetail {
  id: number; vendor_id: number; attempt_no: number; vendor_name: string; status: "QUEUED" | "RUNNING" | "DONE";
  decision: VendorStatus | null; summary: string | null; created_at: string; started_at: string | null;
  finished_at: string | null; stages: Stage[]; checks: CheckItem[]; llm_calls?: LlmCall[];
}

export interface ComparisonRow {
  field: string; label: string; document: string; typed: string; extracted: string | null;
  confidence: number | null; result: Severity | null; reason: string | null;
}

export interface Attempt {
  submission_id: number; attempt_no: number; submitted_at: string; fields: Record<string, string>;
  documents: { id: number; slot: string; name: string; mime: string; size_bytes: number; reused_from_attempt: number | null }[];
  run: RunDetail | null; comparison: ComparisonRow[];
}

export interface Message {
  id: number; vendor_id: number; run_id: number | null; kind: string; to: string; subject: string; body: string;
  drafted_by: "LLM" | "TEMPLATE"; sent_via: string; created_at: string; vendor_name?: string;
}

export interface Override {
  id: number; decision: "APPROVED" | "REJECTED"; reason: string; status: "PENDING" | "APPLIED" | "DECLINED";
  requested_by: string; requested_by_id: number; reviewed_by: string | null; review_note: string | null;
  created_at: string; reviewed_at: string | null;
}

export interface VendorDetail {
  vendor: VendorRow; attempts: Attempt[]; outbox: Message[];
  audit: { id: number; at: string; actor: string; action: string; details: Record<string, unknown> | null }[];
  overrides: Override[]; in_vendor_master: boolean; portal: { active: boolean; expires_at: string | null };
  can_admin: boolean; four_eyes: boolean;
}

export interface Scenario { key: string; title: string; description: string; expected: string; has_fix: boolean }

export interface PortalState {
  company: string; buyer_name: string; contact_email: string; status: VendorStatus; status_label: string;
  can_submit: boolean; attempt_no: number; max_attempts: number; last_submitted_at: string | null;
  prefill: Record<string, string>; documents_on_file: { slot: string; name: string }[];
  flags: { field: string | null; message: string }[]; max_file_mb: number;
}
