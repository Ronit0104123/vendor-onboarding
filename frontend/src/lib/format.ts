import type { Severity, VendorStatus } from "./types";

const dateTime = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const dateOnly = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

export const fmtDateTime = (iso?: string | null) => (iso ? dateTime.format(new Date(iso)) : "—");
export const fmtDate = (iso?: string | null) => (iso ? dateOnly.format(new Date(iso)) : "—");

export function fmtRelative(iso?: string | null): string {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return fmtDate(iso);
}

export const fmtMs = (ms?: number | null) =>
  ms == null ? "" : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;

export const fmtHours = (h: number | null) =>
  h == null ? "—" : h < 1 ? `${Math.round(h * 60)} min` : h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`;

export const STATUS_LABEL: Record<VendorStatus, string> = {
  INVITED: "Invited", SUBMITTED: "Queued", PROCESSING: "Checking", PENDING_VENDOR: "Waiting on vendor",
  PENDING_INTERNAL: "Needs review", APPROVED: "Approved", REJECTED: "Rejected", AUTO_CLOSED: "Closed",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  PASS: "Pass", WARN: "Warning", FIXABLE: "Fixable", BLOCKING: "Blocking", NEEDS_REVIEW: "Review",
};

export const SLOT_LABEL: Record<string, string> = {
  GST_CERT: "GST certificate", PAN_CARD: "PAN card", BANK_PROOF: "Cancelled cheque / bank letter",
};

export const MESSAGE_KIND: Record<string, string> = {
  INVITE: "Invitation", FIX_REQUEST: "Items to fix", REJECTION: "Rejection", INTERNAL_ALERT: "Internal alert",
  WELCOME: "Welcome", REMINDER: "Reminder", ACKNOWLEDGEMENT: "Acknowledgement", CLOSED: "Closed",
};
