import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Radio } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { RunDetail, Stage } from "@/lib/types";
import { fmtDateTime, fmtMs, MESSAGE_KIND } from "@/lib/format";
import { Page } from "@/components/AppShell";
import { StatusBadge } from "@/components/badges";
import { CheckList, StageList } from "@/components/StageList";
import { Button } from "@/components/ui/button";
import { ErrorState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";

function describe(s: Stage) {
  return { pass: "passed", warn: "passed with warnings", fail: "found issues", review: "needs review", running: "started", pending: "waiting" }[s.status];
}

export default function RunLive() {
  const { id } = useParams();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const prev = useRef<Record<string, string>>({});

  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;
    setRun(null);
    prev.current = {};
    const accept = (r: RunDetail) => {
      const changes = r.stages.filter((s) => prev.current[s.stage] !== s.status && s.status !== "pending");
      if (changes.length) {
        const last = changes[changes.length - 1];
        setAnnouncement(`${last.stage} ${last.name} ${describe(last)}.` + (r.status === "DONE" && r.decision ? ` Decision: ${r.decision.replace("_", " ").toLowerCase()}.` : ""));
      }
      prev.current = Object.fromEntries(r.stages.map((s) => [s.stage, s.status]));
      setRun(r);
    };
    api.get<RunDetail>(`/api/runs/${id}`).then((r) => {
      if (cancelled) return;
      accept(r);
      if (r.status !== "DONE") {
        es = new EventSource(`/api/runs/${id}/events`);
        es.onopen = () => setLive(true);
        es.addEventListener("run", (e) => accept(JSON.parse((e as MessageEvent).data)));
        es.addEventListener("done", async () => {
          es?.close();
          setLive(false);
          accept(await api.get<RunDetail>(`/api/runs/${id}`)); // full detail incl. LLM calls
        });
        es.onerror = () => setLive(false); // browser auto-reconnects; the stream resumes from current state
      }
    }).catch((e: ApiError) => setError(e.message));
    return () => { cancelled = true; es?.close(); };
  }, [id]);

  if (error) return <Page title="Pipeline run"><Panel><ErrorState message={error} /></Panel></Page>;

  const done = run?.status === "DONE";
  const s9 = run?.stages.find((s) => s.stage === "S9");
  const messages = (s9?.output?.messages as { kind: string; to: string; subject: string; drafted_by: string }[] | undefined) ?? [];
  const deciding = run ? run.checks.filter((c) => ["BLOCKING", "FIXABLE", "NEEDS_REVIEW"].includes(c.severity)) : [];
  const totalMs = run?.stages.reduce((a, s) => a + (s.duration_ms ?? 0), 0) ?? 0;

  return (
    <Page
      breadcrumb={run ? <Link to={`/vendors/${run.vendor_id}`} className="hover:text-ink hover:underline">{run.vendor_name}</Link> : <Skeleton className="w-40" />}
      title={run ? `Attempt ${run.attempt_no} · run #${run.id}` : "Pipeline run"}
      description={run ? <>Started {fmtDateTime(run.started_at ?? run.created_at)}{done && <> · finished in <span className="num">{fmtMs(totalMs)}</span></>}</> : " "}
      actions={
        <div className="flex items-center gap-2">
          {!done && run && (
            <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 text-xs font-medium text-ink-2">
              <Radio className={live ? "size-3.5 text-accent" : "size-3.5 text-muted"} aria-hidden />
              {run.status === "QUEUED" ? "Queued" : live ? "Live" : "Reconnecting"}
            </span>
          )}
          {done && run?.decision && <StatusBadge status={run.decision} />}
        </div>
      }
    >
      <div aria-live="polite" aria-atomic="true" className="sr-only">{announcement}</div>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Panel>
          <PanelHeader title="Pipeline stages" description="Each stage runs in order. Open a stage to see exactly what went in and what came out." />
          {run ? <StageList stages={run.stages} checks={run.checks} defaultOpen={[]} /> : (
            <div className="divide-y divide-line">{Array.from({ length: 9 }).map((_, i) => <div key={i} className="flex h-[49px] items-center gap-3 px-4"><Skeleton className="size-[18px] rounded-full" /><Skeleton className="w-48" /></div>)}</div>
          )}
        </Panel>

        <div className="flex flex-col gap-5">
          <Panel>
            <PanelHeader title="Decision" />
            <div className="p-4">
              {!done ? (
                <p className="text-[13px] text-muted">{run?.status === "QUEUED" ? "Waiting for a worker to pick this up." : "The decision is made by fixed rules once every check has run. The AI model never decides."}</p>
              ) : (
                <>
                  <div className="flex items-center gap-2">{run?.decision && <StatusBadge status={run.decision} />}<span className="text-[13px] text-ink-2">{run?.summary}</span></div>
                  {deciding.length > 0 && <div className="mt-4"><CheckList checks={deciding} compact /></div>}
                  <Link to={`/vendors/${run!.vendor_id}`} className="mt-4 inline-block"><Button size="sm">Open vendor record <ArrowRight aria-hidden /></Button></Link>
                </>
              )}
            </div>
          </Panel>
          {done && (
            <Panel>
              <PanelHeader title="Messages sent" />
              {messages.length ? (
                <ul className="divide-y divide-line">
                  {messages.map((m, i) => (
                    <li key={i} className="px-4 py-3 text-[13px]">
                      <p className="font-medium">{m.subject}</p>
                      <p className="mt-0.5 text-xs text-muted">{MESSAGE_KIND[m.kind] ?? m.kind} · to {m.to} · {m.drafted_by === "LLM" ? "drafted by AI, list inserted by system" : "template"}</p>
                    </li>
                  ))}
                </ul>
              ) : <p className="p-4 text-[13px] text-muted">No messages.</p>}
            </Panel>
          )}
        </div>
      </div>
    </Page>
  );
}
