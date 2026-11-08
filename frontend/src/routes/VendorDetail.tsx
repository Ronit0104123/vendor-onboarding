import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { BellRing, Download, ExternalLink, Eye, EyeOff, Gavel, Link2, PlayCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import type { Attempt, ComparisonRow, Message, VendorDetail as VD } from "@/lib/types";
import { fmtDateTime, MESSAGE_KIND, SLOT_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Page } from "@/components/AppShell";
import { SeverityBadge, StatusBadge } from "@/components/badges";
import { CheckList, StageList } from "@/components/StageList";
import { CopyButton } from "@/components/NewVendorDialog";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/input";
import { EmptyState, ErrorState, Panel, PanelHeader, Skeleton, Spinner } from "@/components/ui/misc";
import { TabPanel, Tabs } from "@/components/ui/tabs";

const FIELD_ROWS: [string, string][] = [
  ["legal_name", "Legal name"], ["trade_name", "Trade name"], ["country", "Country"], ["address_line", "Address"],
  ["city", "City"], ["state", "State"], ["postal_code", "PIN / postal code"], ["contact_name", "Contact"],
  ["contact_email", "Contact email"], ["contact_phone", "Phone"], ["pan", "PAN"], ["gstin", "GSTIN"], ["tax_id", "Tax ID"],
  ["bank_holder_name", "Account holder"], ["account_number", "Account number"], ["bank_code", "IFSC / bank code"],
];

function Comparison({ rows }: { rows: ComparisonRow[] }) {
  if (!rows.length) return <p className="px-4 py-6 text-[13px] text-muted">No document values were extracted for this attempt.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-[13px]">
        <thead className="text-xs text-muted"><tr className="border-b border-line">
          <th scope="col" className="px-4 py-2 font-medium">Field</th>
          <th scope="col" className="px-3 py-2 font-medium">Entered by vendor</th>
          <th scope="col" className="px-3 py-2 font-medium">Read from document</th>
          <th scope="col" className="px-3 py-2 text-right font-medium">Confidence</th>
          <th scope="col" className="px-4 py-2 font-medium">Result</th>
        </tr></thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => {
            const bad = r.result === "BLOCKING" || r.result === "FIXABLE";
            return (
              <tr key={r.field} className={cn(bad && "bg-bad-soft/50", r.result === "NEEDS_REVIEW" && "bg-info-soft/50")}>
                <th scope="row" className="px-4 py-2.5 font-medium text-ink-2">{r.label}<div className="text-xs font-normal text-muted">{SLOT_LABEL[r.document]}</div></th>
                <td className="num px-3 py-2.5 font-mono text-[12.5px]">{r.typed || "—"}</td>
                <td className={cn("num px-3 py-2.5 font-mono text-[12.5px]", bad && "font-semibold text-bad")}>{r.extracted ?? "—"}</td>
                <td className={cn("num px-3 py-2.5 text-right", (r.confidence ?? 1) < 0.75 && "text-info font-medium")}>{r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "—"}</td>
                <td className="px-4 py-2.5">{r.result ? <SeverityBadge severity={r.result} /> : <span className="text-xs text-muted">—</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RevealValue({ masked, submissionId, field, canReveal }: { masked: string; submissionId: number; field: "pan" | "account_number"; canReveal: boolean }) {
  const [value, setValue] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!value) return; const t = setTimeout(() => setValue(null), 30000); return () => clearTimeout(t); }, [value]);
  if (!masked) return <span className="text-muted">—</span>;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="num font-mono text-[12.5px]">{value ?? masked}</span>
      {canReveal && (
        <button className="inline-flex items-center gap-1 text-xs text-accent hover:underline disabled:opacity-50" disabled={busy}
          onClick={async () => {
            if (value) return setValue(null);
            setBusy(true);
            try { setValue((await api.post<{ value: string }>(`/api/submissions/${submissionId}/reveal`, { field })).value); } finally { setBusy(false); }
          }}>
          {value ? <EyeOff className="size-3.5" aria-hidden /> : <Eye className="size-3.5" aria-hidden />}{value ? "Hide" : "Reveal"}
        </button>
      )}
    </span>
  );
}

function AttemptView({ a, canAdmin }: { a: Attempt; canAdmin: boolean }) {
  const [tab, setTab] = useState("checks");
  const run = a.run;
  const issues = run?.checks.filter((c) => c.severity !== "PASS") ?? [];
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold">Attempt {a.attempt_no}</h2>
            {run?.decision && <StatusBadge status={run.decision} />}
          </div>
          <p className="mt-0.5 text-[13px] text-muted">Submitted {fmtDateTime(a.submitted_at)}{run?.summary && ` · ${run.summary}`}</p>
        </div>
        {run && <Link to={`/runs/${run.id}`}><Button size="sm"><PlayCircle aria-hidden />{run.status === "DONE" ? "Run trace" : "Watch live"}</Button></Link>}
      </div>
      <Tabs label="Attempt sections" value={tab} onChange={setTab} tabs={[
        { key: "checks", label: <>Checks {issues.length > 0 && <span className="num ml-1 rounded bg-subtle px-1 text-xs text-muted">{issues.length}</span>}</> },
        { key: "compare", label: "Documents vs form" },
        { key: "details", label: "Submitted details" },
        { key: "pipeline", label: "Pipeline & AI calls" },
      ]} />
      <TabPanel id="checks" active={tab === "checks"}>
        <div className="p-4">{run ? <CheckList checks={run.checks} /> : <p className="text-[13px] text-muted">Not processed yet.</p>}</div>
      </TabPanel>
      <TabPanel id="compare" active={tab === "compare"}>
        <Comparison rows={a.comparison} />
      </TabPanel>
      <TabPanel id="details" active={tab === "details"}>
        <div className="grid gap-6 p-4 lg:grid-cols-[1fr_280px]">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 text-[13px] sm:grid-cols-[160px_1fr]">
            {FIELD_ROWS.filter(([k]) => a.fields[k]).map(([k, label]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{label}</dt>
                <dd className="min-w-0 break-words text-ink">
                  {k === "pan" || k === "account_number"
                    ? <RevealValue masked={a.fields[k]} submissionId={a.submission_id} field={k} canReveal={canAdmin} />
                    : k === "gstin" ? <span className="num font-mono text-[12.5px]">{a.fields[k]}</span> : a.fields[k]}
                </dd>
              </div>
            ))}
          </dl>
          <div>
            <h3 className="mb-2 text-xs font-semibold text-ink-2">Documents</h3>
            <ul className="flex flex-col gap-2">
              {a.documents.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2 rounded-md border border-line px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium">{SLOT_LABEL[d.slot]}</p>
                    <p className="truncate text-xs text-muted">{d.reused_from_attempt ? `Kept from attempt ${d.reused_from_attempt}` : d.name} · {Math.round(d.size_bytes / 1024)} KB</p>
                  </div>
                  <a href={`/api/documents/${d.id}`} aria-label={`Download ${SLOT_LABEL[d.slot]}`} className="rounded-md p-1.5 text-muted hover:bg-hover hover:text-ink"><Download className="size-4" aria-hidden /></a>
                </li>
              ))}
              {!a.documents.length && <li className="text-[13px] text-muted">No documents uploaded.</li>}
            </ul>
          </div>
        </div>
      </TabPanel>
      <TabPanel id="pipeline" active={tab === "pipeline"}>
        {run && <StageList stages={run.stages} checks={run.checks} />}
        {run?.llm_calls && run.llm_calls.length > 0 && (
          <div className="overflow-x-auto border-t border-line">
            <table className="w-full min-w-[560px] text-left text-[13px]">
              <caption className="px-4 pt-3 text-left text-xs font-semibold text-ink-2">AI model calls (prompts and outputs are stored with PAN and account numbers redacted)</caption>
              <thead className="text-xs text-muted"><tr className="border-b border-line">
                <th scope="col" className="px-4 py-2 font-medium">Purpose</th><th scope="col" className="px-3 py-2 font-medium">Model</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Latency</th><th scope="col" className="px-3 py-2 text-right font-medium">Tokens</th>
                <th scope="col" className="px-4 py-2 font-medium">Result</th></tr></thead>
              <tbody className="divide-y divide-line">
                {run.llm_calls.map((c, i) => (
                  <tr key={i}>
                    <td className="px-4 py-2">{c.prompt_summary}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted">{c.model}</td>
                    <td className="num px-3 py-2 text-right">{c.latency_ms} ms</td>
                    <td className="num px-3 py-2 text-right">{c.tokens_in + c.tokens_out || "—"}</td>
                    <td className="px-4 py-2">{c.ok ? <span className="text-ok">OK{c.attempts > 1 && " (after retry)"}</span> : <span className="text-bad">Failed: {c.error}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </TabPanel>
    </Panel>
  );
}

function MessageItem({ m }: { m: Message }) {
  const [open, setOpen] = useState(false);
  return (
    <li>
      <button className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-subtle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium">{m.subject}</p>
          <p className="text-xs text-muted">{MESSAGE_KIND[m.kind] ?? m.kind} · to {m.to} · {m.drafted_by === "LLM" ? "AI-drafted wording" : "template"} · {m.sent_via === "RESEND" ? "emailed" : "logged"}</p>
        </div>
        <span className="num shrink-0 text-xs text-muted">{fmtDateTime(m.created_at)}</span>
      </button>
      {open && <pre className="mx-4 mb-3 whitespace-pre-wrap break-words rounded-md border border-line bg-subtle p-3 font-sans text-[13px] text-ink-2">{m.body}</pre>}
    </li>
  );
}

const ACTION_LABEL: Record<string, string> = {
  VENDOR_REQUESTED: "Vendor request created", MESSAGE_SENT: "Message sent", SUBMITTED: "Vendor submitted",
  DECISION: "Pipeline decision", VENDOR_MASTER_ADDED: "Added to vendor master", PII_REVEALED: "Sensitive value revealed",
  OVERRIDE_REQUESTED: "Override requested", OVERRIDE_APPLIED: "Override applied", OVERRIDE_DECLINED: "Override declined",
  REMINDER_SENT: "Reminder sent", PORTAL_LINK_VIEWED: "Portal link viewed", PORTAL_LINK_REISSUED: "Portal link reissued",
  DOCUMENT_DOWNLOADED: "Document downloaded", RUN_FAILED: "Run failed",
};

function OverrideDialog({ open, onClose, vendorId, fourEyes, onDone }: { open: boolean; onClose: () => void; vendorId: number; fourEyes: boolean; onDone: () => void }) {
  const [decision, setDecision] = useState<"APPROVED" | "REJECTED">("APPROVED");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true); setError(null);
    try { await api.post(`/api/vendors/${vendorId}/overrides`, { decision, reason }); setReason(""); onDone(); onClose(); }
    catch (e) { setError((e as ApiError).fields.reason ?? (e as ApiError).message); }
    finally { setBusy(false); }
  }
  return (
    <Dialog open={open} onClose={onClose} title="Override decision"
      description={fourEyes ? "A second admin must approve this before it takes effect. Both steps are recorded in the audit trail." : "This takes effect immediately and is recorded in the audit trail."}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || reason.trim().length < 15} onClick={submit}>{busy && <Spinner />}{fourEyes ? "Submit for approval" : "Apply override"}</Button></>}>
      <fieldset className="mb-4">
        <legend className="mb-2 text-[13px] font-medium text-ink-2">Decision</legend>
        <div className="grid grid-cols-2 gap-2">
          {(["APPROVED", "REJECTED"] as const).map((d) => (
            <label key={d} className={cn("flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-[13px]", decision === d ? "border-accent bg-accent-soft" : "border-line-strong")}>
              <input type="radio" name="decision" value={d} checked={decision === d} onChange={() => setDecision(d)} className="accent-[var(--color-accent)]" />
              {d === "APPROVED" ? "Approve vendor" : "Reject vendor"}
            </label>
          ))}
        </div>
      </fieldset>
      <Field id="reason" label="Reason" hint="Required, at least 15 characters. Say what you checked and where the evidence is." error={error}>
        <Textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} aria-invalid={!!error} placeholder="e.g. Confirmed the GST name change via the registration amendment on file (REG-14)." />
      </Field>
    </Dialog>
  );
}

export default function VendorDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const { data, error, loading, reload } = useApi<VD>(`/api/vendors/${id}`);
  const [selected, setSelected] = useState<number | null>(null);
  const [tab, setTab] = useState("attempts");
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => { setSelected(null); }, [id]);
  // Keep the page fresh while a run is in progress.
  const processing = data && ["SUBMITTED", "PROCESSING"].includes(data.vendor.status);
  useEffect(() => { if (!processing) return; const t = setInterval(() => reload(true), 2000); return () => clearInterval(t); }, [processing, reload]);

  if (error) return <Page title="Vendor"><Panel><ErrorState message={error.status === 404 ? "This vendor doesn't exist or was removed." : error.message} onRetry={() => reload()} /></Panel></Page>;
  if (loading && !data) return <Page title={<Skeleton className="h-6 w-64" />} description={<Skeleton className="mt-1 w-80" />}><Panel className="p-4"><Skeleton className="mb-3 w-1/2" /><Skeleton className="mb-3 w-2/3" /><Skeleton className="w-1/3" /></Panel></Page>;
  if (!data) return null;

  const v = data.vendor;
  const attempt = data.attempts.find((a) => a.attempt_no === selected) ?? data.attempts[data.attempts.length - 1];
  const pendingOverride = data.overrides.find((o) => o.status === "PENDING");
  const isAdmin = data.can_admin;

  async function act(fn: () => Promise<unknown>, ok: string) {
    setActionError(null);
    try { await fn(); setNotice(ok); reload(true); } catch (e) { setActionError((e as ApiError).message); }
  }

  return (
    <Page
      breadcrumb={<><Link to="/" className="hover:text-ink hover:underline">Vendors</Link> <span aria-hidden>/</span> <span className="num">{v.ref}</span></>}
      title={<span className="flex flex-wrap items-center gap-2.5">{v.display_name}<StatusBadge status={v.status} /></span>}
      description={<span className="num">{v.category} · {v.contact_email} · requested by {v.requested_by} · attempt {v.attempt_count} of {v.max_attempts}{data.in_vendor_master && " · in vendor master"}</span>}
      actions={isAdmin && (
        <>
          {data.portal.active && (
            <Button size="sm" onClick={() => act(async () => setLinkOpen((await api.post<{ portal_url: string }>(`/api/vendors/${v.id}/portal-link`)).portal_url), "")}>
              <Link2 aria-hidden /> Portal link
            </Button>
          )}
          {v.status === "PENDING_VENDOR" && (
            <Button size="sm" onClick={() => act(() => api.post(`/api/vendors/${v.id}/remind`), "Reminder logged in the outbox.")}>
              <BellRing aria-hidden /> Send reminder
            </Button>
          )}
          {v.status === "PENDING_INTERNAL" && !pendingOverride && (
            <Button size="sm" variant="primary" onClick={() => setOverrideOpen(true)}><Gavel aria-hidden /> Override</Button>
          )}
        </>
      )}
    >
      <div aria-live="polite" className="sr-only">{notice}</div>
      {actionError && <p role="alert" className="mb-4 rounded-md border border-bad/20 bg-bad-soft px-3 py-2 text-[13px] text-bad">{actionError}</p>}
      {v.reminder_due && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-warn/20 bg-warn-soft px-3 py-2 text-[13px] text-warn">
          <BellRing className="size-4 shrink-0" aria-hidden /> Waiting on the vendor for {v.days_waiting} days. A reminder is due.
        </div>
      )}
      {pendingOverride && (
        <Panel className="mb-4 border-info/25">
          <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="text-[13px]">
              <p className="font-medium">Override waiting for a second admin: {pendingOverride.decision === "APPROVED" ? "approve" : "reject"} this vendor</p>
              <p className="mt-1 text-ink-2">“{pendingOverride.reason}”</p>
              <p className="mt-1 text-xs text-muted">Requested by {pendingOverride.requested_by} · {fmtDateTime(pendingOverride.created_at)}</p>
            </div>
            {isAdmin && (pendingOverride.requested_by_id === me?.id ? (
              <p className="text-xs text-muted sm:max-w-48">You requested this, so another admin has to approve it.</p>
            ) : (
              <div className="flex shrink-0 gap-2">
                <Button size="sm" onClick={() => act(() => api.post(`/api/overrides/${pendingOverride.id}/review`, { approve: false, note: "Declined on review" }), "Override declined.")}>Decline</Button>
                <Button size="sm" variant="primary" onClick={() => act(() => api.post(`/api/overrides/${pendingOverride.id}/review`, { approve: true, note: "Approved on review" }), "Override applied.")}>Approve override</Button>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Tabs label="Vendor sections" value={tab} onChange={setTab} tabs={[
        { key: "attempts", label: "Attempts" },
        { key: "messages", label: <>Messages <span className="num ml-1 text-xs text-muted">{data.outbox.length}</span></> },
        { key: "audit", label: <>Audit trail <span className="num ml-1 text-xs text-muted">{data.audit.length}</span></> },
      ]} />
      <div className="mt-4">
        <TabPanel id="attempts" active={tab === "attempts"}>
          {!data.attempts.length ? (
            <Panel><EmptyState title="No submission yet" body="The vendor hasn't opened their link or submitted the form." /></Panel>
          ) : (
            <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[200px_minmax(0,1fr)]">
              <nav aria-label="Attempt history">
                <ol className="relative flex gap-2 overflow-x-auto lg:flex-col lg:gap-0 lg:overflow-visible">
                  {data.attempts.map((a, i) => {
                    const active = a.attempt_no === attempt.attempt_no;
                    return (
                      <li key={a.attempt_no} className="relative lg:pb-4 lg:pl-5">
                        {i < data.attempts.length - 1 && <span aria-hidden className="absolute left-[5px] top-3 hidden h-full w-px bg-line lg:block" />}
                        <span aria-hidden className={cn("absolute left-0 top-[7px] hidden size-[11px] rounded-full border-2 bg-surface lg:block", active ? "border-accent" : "border-line-strong")} />
                        <button onClick={() => setSelected(a.attempt_no)} aria-current={active ? "step" : undefined}
                          className={cn("w-full whitespace-nowrap rounded-md border px-3 py-2 text-left lg:border-transparent lg:px-2 lg:py-1", active ? "border-accent bg-surface lg:bg-accent-soft/60" : "border-line hover:bg-hover")}>
                          <span className="block text-[13px] font-medium">Attempt {a.attempt_no}</span>
                          <span className="num block text-xs text-muted">{fmtDateTime(a.submitted_at)}</span>
                          {a.run?.decision && <StatusBadge status={a.run.decision} className="mt-1.5" />}
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </nav>
              <AttemptView key={attempt.attempt_no} a={attempt} canAdmin={isAdmin} />
            </div>
          )}
        </TabPanel>
        <TabPanel id="messages" active={tab === "messages"}>
          <Panel>
            <PanelHeader title="Messages" description="Everything sent to the vendor or the procurement team for this case." />
            {data.outbox.length ? <ul className="divide-y divide-line">{[...data.outbox].reverse().map((m) => <MessageItem key={m.id} m={m} />)}</ul> : <EmptyState title="No messages yet" />}
          </Panel>
        </TabPanel>
        <TabPanel id="audit" active={tab === "audit"}>
          <Panel>
            <PanelHeader title="Audit trail" description="Append-only. Entries can't be edited or deleted, including by admins." />
            <ol className="divide-y divide-line">
              {[...data.audit].reverse().map((e) => (
                <li key={e.id} className="grid gap-1 px-4 py-2.5 text-[13px] sm:grid-cols-[150px_1fr]">
                  <span className="num text-xs text-muted">{fmtDateTime(e.at)}</span>
                  <div className="min-w-0">
                    <span className="font-medium">{ACTION_LABEL[e.action] ?? e.action}</span>
                    <span className="text-muted"> · {e.actor}</span>
                    {e.details && <p className="mt-0.5 break-words font-mono text-[11.5px] text-muted">{Object.entries(e.details).map(([k, val]) => `${k}: ${Array.isArray(val) ? val.join(", ") : String(val)}`).join(" · ")}</p>}
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </TabPanel>
      </div>

      <OverrideDialog open={overrideOpen} onClose={() => setOverrideOpen(false)} vendorId={v.id} fourEyes={data.four_eyes} onDone={() => { setNotice("Override submitted."); reload(true); }} />
      <Dialog open={!!linkOpen} onClose={() => setLinkOpen(null)} title="Vendor portal link"
        description="Viewing this link is recorded in the audit trail. Share it only with the vendor's contact.">
        <div className="flex items-center gap-2 rounded-md border border-line bg-subtle p-2">
          <code className="num min-w-0 flex-1 truncate font-mono text-xs">{linkOpen}</code>
          {linkOpen && <CopyButton text={linkOpen} />}
        </div>
        {linkOpen && <a href={linkOpen} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-[13px] text-accent hover:underline">Open as vendor <ExternalLink className="size-3.5" aria-hidden /></a>}
      </Dialog>
    </Page>
  );
}
