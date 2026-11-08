import { CheckCircle2, CircleDashed, CircleAlert, CircleX, Clock, Eye, Loader, MinusCircle, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import { SEVERITY_LABEL, STATUS_LABEL } from "@/lib/format";
import type { Severity, VendorStatus } from "@/lib/types";

const tone = {
  ok: "bg-ok-soft text-ok border-ok/15",
  warn: "bg-warn-soft text-warn border-warn/15",
  bad: "bg-bad-soft text-bad border-bad/15",
  info: "bg-info-soft text-info border-info/15",
  neutral: "bg-subtle text-ink-2 border-line",
} as const;

const STATUS_TONE: Record<VendorStatus, keyof typeof tone> = {
  APPROVED: "ok", REJECTED: "bad", PENDING_VENDOR: "warn", PENDING_INTERNAL: "info",
  AUTO_CLOSED: "neutral", INVITED: "neutral", SUBMITTED: "neutral", PROCESSING: "neutral",
};
const STATUS_ICON: Record<VendorStatus, typeof Clock> = {
  APPROVED: CheckCircle2, REJECTED: CircleX, PENDING_VENDOR: Clock, PENDING_INTERNAL: Eye,
  AUTO_CLOSED: MinusCircle, INVITED: CircleDashed, SUBMITTED: Loader, PROCESSING: Loader,
};

export function StatusBadge({ status, className }: { status: VendorStatus; className?: string }) {
  const Icon = STATUS_ICON[status];
  return (
    <span className={cn("inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full border px-2 text-xs font-medium", tone[STATUS_TONE[status]], className)}>
      <Icon className="size-3.5" aria-hidden />
      {STATUS_LABEL[status]}
    </span>
  );
}

const SEV_TONE: Record<Severity, keyof typeof tone> = {
  PASS: "ok", WARN: "neutral", FIXABLE: "warn", BLOCKING: "bad", NEEDS_REVIEW: "info",
};
const SEV_ICON: Record<Severity, typeof Clock> = {
  PASS: CheckCircle2, WARN: CircleAlert, FIXABLE: Wrench, BLOCKING: CircleX, NEEDS_REVIEW: Eye,
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const Icon = SEV_ICON[severity];
  return (
    <span className={cn("inline-flex h-[22px] w-[84px] shrink-0 items-center gap-1 rounded-md border px-1.5 text-[11.5px] font-medium", tone[SEV_TONE[severity]], className)}>
      <Icon className="size-3.5" aria-hidden />
      {SEVERITY_LABEL[severity]}
    </span>
  );
}
