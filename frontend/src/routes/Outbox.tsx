import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Mail } from "lucide-react";
import { useApi } from "@/lib/hooks";
import type { Message } from "@/lib/types";
import { fmtDateTime, MESSAGE_KIND } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Page } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/misc";

const PAGE = 25;

export default function Outbox() {
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const { data, error, loading, reload } = useApi<{ items: Message[]; total: number }>(`/api/outbox?page=${page}&page_size=${PAGE}`);
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE));
  return (
    <Page title="Outbox" description="Every message the system has sent or logged, newest first. This is the communication audit trail.">
      <Panel>
        {error ? <ErrorState message={error.message} onRetry={() => reload()} /> : loading && !data ? (
          <div className="divide-y divide-line">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="flex h-[58px] items-center gap-4 px-4"><Skeleton className="w-72" /><Skeleton className="ml-auto w-20" /></div>)}</div>
        ) : !data?.items.length ? <EmptyState icon={<Mail className="size-4" aria-hidden />} title="No messages yet" /> : (
          <>
            <ul className={cn("divide-y divide-line", loading && "opacity-60")}>
              {data.items.map((m) => (
                <li key={m.id}>
                  <button className="grid w-full gap-1 px-4 py-3 text-left hover:bg-subtle sm:grid-cols-[150px_1fr_auto] sm:gap-4" aria-expanded={open === m.id} onClick={() => setOpen(open === m.id ? null : m.id)}>
                    <span className="text-xs font-medium text-ink-2">{MESSAGE_KIND[m.kind] ?? m.kind}</span>
                    <span className="min-w-0"><span className="block truncate text-[13px] font-medium">{m.subject}</span><span className="block truncate text-xs text-muted">{m.vendor_name} · to {m.to} · {m.drafted_by === "LLM" ? "AI-drafted wording" : "template"}</span></span>
                    <span className="num text-xs text-muted">{fmtDateTime(m.created_at)}</span>
                  </button>
                  {open === m.id && (
                    <div className="px-4 pb-4">
                      <pre className="whitespace-pre-wrap break-words rounded-md border border-line bg-subtle p-3 font-sans text-[13px] text-ink-2">{m.body}</pre>
                      <Link to={`/vendors/${m.vendor_id}`} className="mt-2 inline-block text-[13px] text-accent hover:underline">Open vendor</Link>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-[13px] text-muted">
              <span className="num">Page {page} of {pages}</span>
              <div className="flex gap-1">
                <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft aria-hidden /></Button>
                <Button size="icon" variant="ghost" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight aria-hidden /></Button>
              </div>
            </div>
          </>
        )}
      </Panel>
    </Page>
  );
}
