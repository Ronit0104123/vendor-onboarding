import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Clock, Play, RotateCcw } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import type { Scenario, Stats } from "@/lib/types";
import { Page } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { ErrorState, Panel, PanelHeader, Skeleton, Spinner } from "@/components/ui/misc";

const KEY = "demo-vendors";
function remembered(): Record<string, number> {
  try { return JSON.parse(sessionStorage.getItem(KEY) ?? "{}"); } catch { return {}; }
}
function remember(scenario: string, vendorId: number) {
  try { sessionStorage.setItem(KEY, JSON.stringify({ ...remembered(), [scenario]: vendorId })); } catch { /* storage may be blocked */ }
}

export default function Demo() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const scenarios = useApi<Scenario[]>("/api/demo/scenarios");
  const stats = useApi<Stats>("/api/stats");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vendors, setVendors] = useState(remembered);
  const isAdmin = me?.role === "ADMIN";

  async function run(key: string, resubmit = false) {
    setBusy(key + (resubmit ? "-fix" : ""));
    setError(null);
    try {
      const url = resubmit ? `/api/demo/scenarios/${key}/resubmit/${vendors[key]}` : `/api/demo/scenarios/${key}`;
      const r = await api.post<{ vendor_id: number; run_id: number }>(url);
      remember(key, r.vendor_id);
      setVendors(remembered());
      navigate(`/runs/${r.run_id}`);
    } catch (e) {
      setError((e as ApiError).message);
      setBusy(null);
    }
  }

  async function shiftClock(days: number) {
    await api.post("/api/clock", { offset_days: days });
    stats.reload(true);
  }

  return (
    <Page title="Demo scenarios" description="Each scenario submits prepared sample documents through the same vendor-portal path a real vendor uses, then opens the live run.">
      {error && <p role="alert" className="mb-4 rounded-md border border-bad/20 bg-bad-soft px-3 py-2 text-[13px] text-bad">{error}</p>}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <Panel>
          <PanelHeader title="Scenarios" description="Running the same scenario twice is caught as a duplicate bank account and PAN, as it would be in production." />
          {scenarios.error ? <ErrorState message={scenarios.error.message} onRetry={() => scenarios.reload()} /> : !scenarios.data ? (
            <div className="divide-y divide-line">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="p-4"><Skeleton className="mb-2 w-48" /><Skeleton className="w-full" /></div>)}</div>
          ) : (
            <ul className="divide-y divide-line">
              {scenarios.data.map((s) => (
                <li key={s.key} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-[13.5px] font-semibold">{s.title}</h3>
                      <span className="num rounded border border-line bg-subtle px-1.5 py-px font-mono text-[11px] text-ink-2">expect {s.expected}</span>
                    </div>
                    <p className="mt-1 text-[13px] text-muted">{s.description}</p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {s.has_fix && vendors[s.key] && (
                      <Button size="sm" disabled={!isAdmin || !!busy} onClick={() => run(s.key, true)}>
                        {busy === s.key + "-fix" ? <Spinner /> : <RotateCcw aria-hidden />} Vendor resubmits fix
                      </Button>
                    )}
                    <Button size="sm" variant="primary" disabled={!isAdmin || !!busy} onClick={() => run(s.key)}>
                      {busy === s.key ? <Spinner /> : <Play aria-hidden />} Run
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {!isAdmin && <p className="border-t border-line px-4 py-3 text-xs text-muted">Viewers can see scenarios but only admins can run them.</p>}
        </Panel>

        <Panel className="self-start">
          <PanelHeader title="Simulated clock" description="Moves 'today' forward so reminder flags can be shown without waiting." />
          <div className="p-4">
            <p className="flex items-center gap-2 text-[13px]"><Clock className="size-4 text-muted" aria-hidden />
              {stats.data ? <span className="num">{stats.data.clock_offset_days ? `+${stats.data.clock_offset_days} days` : "Real time"}</span> : <Skeleton className="w-20" />}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {[3, 7, 14].map((d) => <Button key={d} size="sm" disabled={!isAdmin} onClick={() => shiftClock(d)}><span className="num">+{d} days</span></Button>)}
              <Button size="sm" variant="ghost" disabled={!isAdmin} onClick={() => shiftClock(0)}>Reset</Button>
            </div>
            {stats.data && <p className="mt-3 text-xs text-muted"><span className="num">{stats.data.reminders_due}</span> vendor{stats.data.reminders_due === 1 ? "" : "s"} currently due a reminder.</p>}
          </div>
        </Panel>
      </div>
    </Page>
  );
}
