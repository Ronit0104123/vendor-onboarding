import { useState } from "react";
import { CheckCircle2, ChevronRight, Circle, CircleAlert, CircleX, Eye } from "lucide-react";
import type { CheckItem, Stage, StageStatus } from "@/lib/types";
import { fmtMs } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SeverityBadge } from "./badges";
import { Spinner } from "./ui/misc";

const STAGE_LABEL: Record<StageStatus, string> = {
  pending: "Waiting", running: "Running", pass: "Passed", warn: "Passed with warnings", fail: "Issues found", review: "Needs review",
};

export function StageIcon({ status }: { status: StageStatus }) {
  const cls = "size-[18px] shrink-0";
  switch (status) {
    case "running": return <Spinner className="size-[18px] text-accent" />;
    case "pass": return <CheckCircle2 className={cn(cls, "text-ok")} aria-hidden />;
    case "warn": return <CircleAlert className={cn(cls, "text-warn")} aria-hidden />;
    case "fail": return <CircleX className={cn(cls, "text-bad")} aria-hidden />;
    case "review": return <Eye className={cn(cls, "text-info")} aria-hidden />;
    default: return <Circle className={cn(cls, "text-line-strong")} aria-hidden />;
  }
}

/** Renders stage output as readable JSON. Treated as untrusted text: React escapes it. */
export function DataBlock({ value }: { value: unknown }) {
  if (value == null) return <p className="text-xs text-muted">Nothing recorded.</p>;
  return (
    <pre className="max-h-80 overflow-auto rounded-md border border-line bg-subtle p-3 font-mono text-[11.5px] leading-relaxed text-ink-2 whitespace-pre-wrap break-words">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function CheckList({ checks, compact }: { checks: CheckItem[]; compact?: boolean }) {
  if (!checks.length) return <p className="text-[13px] text-muted">No checks recorded in this stage.</p>;
  const order = { BLOCKING: 0, FIXABLE: 1, NEEDS_REVIEW: 2, WARN: 3, PASS: 4 };
  return (
    <ul className="flex flex-col gap-2">
      {[...checks].sort((a, b) => order[a.severity] - order[b.severity]).map((c, i) => (
        <li key={i} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-3">
          <SeverityBadge severity={c.severity} />
          <div className="min-w-0 text-[13px]">
            <p className="text-ink">{c.reason}</p>
            {!compact && <p className="num mt-0.5 font-mono text-[11px] text-muted">{c.code}{c.field ? ` · ${c.field}` : ""}</p>}
            {c.vendor_message && c.severity === "FIXABLE" && (
              <p className="mt-1 text-xs text-muted">Asked of vendor: “{c.vendor_message}”</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function StageList({ stages, checks, defaultOpen = [] }: { stages: Stage[]; checks: CheckItem[]; defaultOpen?: string[] }) {
  const [open, setOpen] = useState<Set<string>>(new Set(defaultOpen));
  const toggle = (s: string) => setOpen((prev) => { const n = new Set(prev); if (n.has(s)) n.delete(s); else n.add(s); return n; });
  return (
    <ol className="divide-y divide-line">
      {stages.map((s) => {
        const stageChecks = checks.filter((c) => c.stage === s.stage);
        const issues = stageChecks.filter((c) => c.severity !== "PASS").length;
        const isOpen = open.has(s.stage);
        const canOpen = s.status !== "pending";
        return (
          <li key={s.stage} className={cn("transition-colors duration-200", s.status === "running" && "bg-accent-soft/40")}>
            <button type="button" onClick={() => canOpen && toggle(s.stage)} aria-expanded={canOpen ? isOpen : undefined} disabled={!canOpen}
              aria-controls={`stage-${s.stage}`}
              className="flex w-full items-center gap-3 px-4 py-3 text-left disabled:cursor-default enabled:hover:bg-subtle">
              <StageIcon status={s.status} />
              <span className="num w-6 font-mono text-xs text-muted">{s.stage}</span>
              <span className={cn("flex-1 text-[13.5px] font-medium", s.status === "pending" ? "text-muted" : "text-ink")}>{s.name}</span>
              <span className="hidden text-xs text-muted sm:inline">{STAGE_LABEL[s.status]}{issues > 0 && s.status !== "running" ? ` · ${issues} flagged` : ""}</span>
              <span className="num w-14 text-right text-xs text-muted">{fmtMs(s.duration_ms)}</span>
              <ChevronRight className={cn("size-4 text-muted transition-transform duration-150", isOpen && "rotate-90", !canOpen && "invisible")} aria-hidden />
            </button>
            {isOpen && (
              <div id={`stage-${s.stage}`} className="grid gap-4 border-t border-line bg-canvas px-4 py-4 sm:pl-[60px]">
                {stageChecks.length > 0 && <div><h4 className="mb-2 text-xs font-semibold text-ink-2">Checks</h4><CheckList checks={stageChecks} /></div>}
                <div className="grid gap-3 lg:grid-cols-2">
                  <div className="min-w-0"><h4 className="mb-1.5 text-xs font-semibold text-ink-2">Input</h4><DataBlock value={s.input} /></div>
                  <div className="min-w-0"><h4 className="mb-1.5 text-xs font-semibold text-ink-2">Output</h4><DataBlock value={s.output} /></div>
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
