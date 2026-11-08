import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { BellRing, ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import { useApi, useDebounced } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import type { Stats, VendorRow, VendorStatus } from "@/lib/types";
import { fmtHours, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Page } from "@/components/AppShell";
import { StatusBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/misc";
import { NewVendorDialog } from "@/components/NewVendorDialog";

const FILTERS: { key: string; label: string; statuses?: VendorStatus[] }[] = [
  { key: "all", label: "All" },
  { key: "vendor", label: "Waiting on vendor", statuses: ["PENDING_VENDOR"] },
  { key: "review", label: "Needs review", statuses: ["PENDING_INTERNAL"] },
  { key: "approved", label: "Approved", statuses: ["APPROVED"] },
  { key: "rejected", label: "Rejected", statuses: ["REJECTED"] },
  { key: "open", label: "In progress", statuses: ["INVITED", "SUBMITTED", "PROCESSING"] },
  { key: "closed", label: "Closed", statuses: ["AUTO_CLOSED"] },
];
const PAGE_SIZE = 12;

function Kpi({ label, value, sub, onClick, active, loading }: {
  label: string; value: string | number; sub?: string; onClick?: () => void; active?: boolean; loading?: boolean;
}) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp onClick={onClick} aria-pressed={onClick ? active : undefined}
      className={cn("flex min-h-[84px] flex-col items-start rounded-lg border bg-surface px-4 py-3 text-left transition-colors duration-150",
        onClick && "hover:border-line-strong", active ? "border-accent ring-1 ring-accent" : "border-line")}>
      <span className="text-xs font-medium text-muted">{label}</span>
      {loading ? <Skeleton className="mt-2 h-6 w-12" /> : <span className="num mt-1 text-[22px] font-semibold tracking-tight">{value}</span>}
      {sub && !loading && <span className="text-xs text-muted">{sub}</span>}
    </Comp>
  );
}

export default function Dashboard() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filter = params.get("f") ?? "all";
  const page = Number(params.get("p") ?? 1);
  const reminder = params.get("r") === "1";
  const [q, setQ] = useState(params.get("q") ?? "");
  const query = useDebounced(q.trim(), 250);
  const [newOpen, setNewOpen] = useState(false);

  const statuses = FILTERS.find((f) => f.key === filter)?.statuses;
  const qs = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (statuses) qs.set("status", statuses.join(","));
  if (query) qs.set("q", query);
  if (reminder) qs.set("reminder", "true");

  const stats = useApi<Stats>("/api/stats");
  const list = useApi<{ items: VendorRow[]; total: number }>(`/api/vendors?${qs}`);

  const update = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    Object.entries(next).forEach(([k, v]) => (v === null ? p.delete(k) : p.set(k, v)));
    if (!("p" in next)) p.delete("p");
    setParams(p, { replace: true });
  };

  const s = stats.data;
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Page
      title="Vendors"
      description="Every onboarding request, its current status and what it is waiting on."
      actions={me?.role === "ADMIN" && <Button variant="primary" onClick={() => setNewOpen(true)}><Plus aria-hidden /> New vendor request</Button>}
    >
      <section aria-label="Summary" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Total vendors" value={s?.total ?? 0} loading={stats.loading} onClick={() => update({ f: null })} active={filter === "all"} />
        <Kpi label="Approved" value={s?.by_status.APPROVED ?? 0} loading={stats.loading} onClick={() => update({ f: "approved" })} active={filter === "approved"} />
        <Kpi label="Waiting on vendor" value={s?.by_status.PENDING_VENDOR ?? 0} sub={s?.reminders_due ? `${s.reminders_due} reminder${s.reminders_due > 1 ? "s" : ""} due` : undefined} loading={stats.loading} onClick={() => update({ f: "vendor" })} active={filter === "vendor"} />
        <Kpi label="Needs review" value={s?.by_status.PENDING_INTERNAL ?? 0} sub={s?.overrides_waiting ? `${s.overrides_waiting} override awaiting approval` : undefined} loading={stats.loading} onClick={() => update({ f: "review" })} active={filter === "review"} />
        <Kpi label="Rejected" value={s?.by_status.REJECTED ?? 0} loading={stats.loading} onClick={() => update({ f: "rejected" })} active={filter === "rejected"} />
        <Kpi label="Avg. time to decision" value={fmtHours(s?.avg_hours_to_decision ?? null)} sub={s ? `across ${s.decided} decided` : undefined} loading={stats.loading} />
      </section>

      <Panel className="mt-5">
        <div className="flex flex-col gap-3 border-b border-line p-3 md:flex-row md:items-center">
          <div className="hidden flex-wrap gap-1 md:flex" role="group" aria-label="Filter by status">
            {FILTERS.map((f) => (
              <button key={f.key} onClick={() => update({ f: f.key === "all" ? null : f.key })} aria-pressed={filter === f.key}
                className={cn("h-7 rounded-md px-2.5 text-[13px] font-medium transition-colors duration-150",
                  filter === f.key ? "bg-ink text-white" : "text-ink-2 hover:bg-hover")}>
                {f.label}
              </button>
            ))}
          </div>
          <Select className="md:hidden" aria-label="Filter by status" value={filter} onChange={(e) => update({ f: e.target.value === "all" ? null : e.target.value })}>
            {FILTERS.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
          </Select>
          <div className="flex gap-2 md:ml-auto">
            <button onClick={() => update({ r: reminder ? null : "1" })} aria-pressed={reminder}
              className={cn("inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-[13px] font-medium transition-colors duration-150",
                reminder ? "border-warn/30 bg-warn-soft text-warn" : "border-line-strong bg-surface text-ink-2 hover:bg-hover")}>
              <BellRing className="size-4" aria-hidden /> Reminder due
            </button>
            <div className="relative w-full md:w-64">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
              <Input type="search" aria-label="Search vendors" placeholder="Search vendors" value={q}
                onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null }); }} className="pl-8" />
            </div>
          </div>
        </div>

        {list.error ? (
          <ErrorState message={list.error.message} onRetry={() => list.reload()} />
        ) : list.loading && !list.data ? (
          <div className="divide-y divide-line">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex h-[57px] items-center gap-4 px-4"><Skeleton className="w-56" /><Skeleton className="ml-auto w-24" /><Skeleton className="w-16" /></div>
            ))}
          </div>
        ) : !list.data?.items.length ? (
          <EmptyState title={query || filter !== "all" || reminder ? "No vendors match these filters" : "No vendor requests yet"}
            body={query || filter !== "all" || reminder ? "Try a different status or search term." : "Create a request to invite your first vendor."} />
        ) : (
          <>
            {/* Desktop / tablet table */}
            <table className="hidden w-full text-left text-[13px] md:table">
              <thead className="text-xs text-muted">
                <tr className="border-b border-line">
                  <th scope="col" className="px-4 py-2 font-medium">Vendor</th>
                  <th scope="col" className="px-3 py-2 font-medium">Status</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Attempts</th>
                  <th scope="col" className="hidden px-3 py-2 font-medium lg:table-cell">Requested by</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">Last updated</th>
                </tr>
              </thead>
              <tbody className={cn("divide-y divide-line transition-opacity duration-150", list.loading && "opacity-60")}>
                {list.data.items.map((v) => (
                  <tr key={v.id} className="cursor-pointer hover:bg-subtle" onClick={() => navigate(`/vendors/${v.id}`)}>
                    <td className="px-4 py-2.5">
                      <Link to={`/vendors/${v.id}`} className="font-medium text-ink hover:underline" onClick={(e) => e.stopPropagation()}>{v.display_name}</Link>
                      <div className="num text-xs text-muted">{v.ref} · {v.category}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2"><StatusBadge status={v.status} />
                        {v.reminder_due && <span className="inline-flex items-center gap-1 text-xs text-warn" title={`Waiting ${v.days_waiting} days`}><BellRing className="size-3.5" aria-hidden />{v.days_waiting}d</span>}
                      </div>
                    </td>
                    <td className="num px-3 py-2.5 text-right text-ink-2">{v.attempt_count}<span className="text-muted">/{v.max_attempts}</span></td>
                    <td className="hidden px-3 py-2.5 text-ink-2 lg:table-cell">{v.requested_by}</td>
                    <td className="num px-4 py-2.5 text-right text-ink-2" title={v.updated_at}>{fmtRelative(v.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* Mobile stacked rows */}
            <ul className="divide-y divide-line md:hidden">
              {list.data.items.map((v) => (
                <li key={v.id}>
                  <Link to={`/vendors/${v.id}`} className="block px-4 py-3 hover:bg-subtle">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0"><p className="truncate font-medium">{v.display_name}</p><p className="num text-xs text-muted">{v.ref} · {v.category}</p></div>
                      <StatusBadge status={v.status} />
                    </div>
                    <p className="num mt-1.5 text-xs text-muted">Attempt {v.attempt_count}/{v.max_attempts} · updated {fmtRelative(v.updated_at)}{v.reminder_due && ` · reminder due (${v.days_waiting}d)`}</p>
                  </Link>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-[13px] text-muted">
              <span className="num">{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}</span>
              <div className="flex gap-1">
                <Button size="icon" variant="ghost" aria-label="Previous page" disabled={page <= 1} onClick={() => update({ p: String(page - 1) })}><ChevronLeft aria-hidden /></Button>
                <Button size="icon" variant="ghost" aria-label="Next page" disabled={page >= pages} onClick={() => update({ p: String(page + 1) })}><ChevronRight aria-hidden /></Button>
              </div>
            </div>
          </>
        )}
      </Panel>
      <NewVendorDialog open={newOpen} onClose={() => setNewOpen(false)} onCreated={() => { list.reload(true); stats.reload(true); }} />
    </Page>
  );
}
