import { Link } from "react-router-dom";
import { Activity } from "lucide-react";
import { useApi } from "@/lib/hooks";
import type { VendorStatus } from "@/lib/types";
import { fmtRelative } from "@/lib/format";
import { Page } from "@/components/AppShell";
import { StatusBadge } from "@/components/badges";
import { EmptyState, ErrorState, Panel, Skeleton, Spinner } from "@/components/ui/misc";

interface RunRow { id: number; vendor_id: number; vendor_name: string; attempt_no: number; status: string; decision: VendorStatus | null; created_at: string }

export default function Runs() {
  const { data, error, loading, reload } = useApi<RunRow[]>("/api/runs?limit=30");
  return (
    <Page title="Pipeline runs" description="Every submission creates a run. Open one to watch it live or replay its trace.">
      <Panel>
        {error ? <ErrorState message={error.message} onRetry={() => reload()} /> : loading && !data ? (
          <div className="divide-y divide-line">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="flex h-[52px] items-center gap-4 px-4"><Skeleton className="w-52" /><Skeleton className="ml-auto w-24" /></div>)}</div>
        ) : !data?.length ? <EmptyState icon={<Activity className="size-4" aria-hidden />} title="No runs yet" body="Runs appear here when a vendor submits." /> : (
          <ul className="divide-y divide-line">
            {data.map((r) => (
              <li key={r.id}>
                <Link to={`/runs/${r.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                  <span className="num w-14 font-mono text-xs text-muted">#{r.id}</span>
                  <div className="min-w-0 flex-1"><p className="truncate text-[13px] font-medium">{r.vendor_name}</p><p className="text-xs text-muted">Attempt {r.attempt_no} · {fmtRelative(r.created_at)}</p></div>
                  {r.status === "DONE" && r.decision ? <StatusBadge status={r.decision} /> : <span className="inline-flex items-center gap-1.5 text-xs text-ink-2"><Spinner className="size-3.5 text-accent" />{r.status === "QUEUED" ? "Queued" : "Running"}</span>}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </Page>
  );
}
