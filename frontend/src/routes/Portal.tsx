import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { AlertCircle, Camera, CheckCircle2, FileText, Lock, Upload, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { PortalState } from "@/lib/types";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Skeleton, Spinner } from "@/components/ui/misc";

const IN_STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
  "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
  "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur",
  "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
  "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"];

const COUNTRY = {
  IN: { name: "India", postal: "PIN code", postalRe: /^[1-9][0-9]{5}$/, bank: "IFSC", bankRe: /^[A-Z]{4}0[A-Z0-9]{6}$/, bankEg: "NCBA0001234", taxLabel: "", taxRe: /./ },
  US: { name: "United States", postal: "ZIP code", postalRe: /^[0-9]{5}(-[0-9]{4})?$/, bank: "ABA routing number", bankRe: /^[0-9]{9}$/, bankEg: "021000021", taxLabel: "EIN", taxRe: /^[0-9]{2}-[0-9]{7}$/ },
  GB: { name: "United Kingdom", postal: "Postcode", postalRe: /^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$/, bank: "Sort code", bankRe: /^[0-9]{2}-[0-9]{2}-[0-9]{2}$/, bankEg: "20-00-00", taxLabel: "VAT number", taxRe: /^GB([0-9]{9}|[0-9]{12})$/ },
} as const;
type Country = keyof typeof COUNTRY;

const SLOTS = [
  { slot: "GST_CERT", field: "gst_cert", label: "GST registration certificate", hint: "Form GST REG-06, all pages", inOnly: true },
  { slot: "PAN_CARD", field: "pan_card", label: "PAN card", hint: "Front side, all four corners visible", inOnly: true },
  { slot: "BANK_PROOF", field: "bank_proof", label: "Cancelled cheque or bank letter", hint: "Shows account holder, account number and bank code", inOnly: false },
] as const;
const ACCEPT = ["application/pdf", "image/png", "image/jpeg"];

type Form = Record<string, string>;
const EMPTY: Form = { legal_name: "", trade_name: "", country: "IN", address_line: "", city: "", state: "", postal_code: "",
  contact_name: "", contact_email: "", contact_phone: "", pan: "", gstin: "", tax_id: "", bank_holder_name: "", account_number: "", bank_code: "" };

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="border-t border-line py-6 first:border-t-0 first:pt-0">
      <h2 className="text-[15px] font-semibold">{title}</h2>
      {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

function FileField({ label, hint, file, onFile, onFileError, flagged, onFileName, maxMb }: {
  label: string; hint: string; file: File | null; onFile: (f: File | null) => void; onFileError: string | null;
  flagged: string | null; onFileName: string | null; maxMb: number;
}) {
  const pick = useRef<HTMLInputElement>(null);
  const cam = useRef<HTMLInputElement>(null);
  const id = label.replace(/\W+/g, "-").toLowerCase();
  const error = onFileError ?? flagged;
  return (
    <div className={cn("rounded-md border p-3 sm:col-span-2", error ? "border-bad/40 bg-bad-soft/40" : "border-line-strong")}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <p id={`${id}-label`} className="text-[13px] font-medium">{label}</p>
          <p className="text-xs text-muted">{hint} · PDF, JPG or PNG, up to {maxMb} MB</p>
          {file ? (
            <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-ink"><FileText className="size-4 text-muted" aria-hidden /><span className="truncate">{file.name}</span>
              <button type="button" onClick={() => onFile(null)} className="rounded p-0.5 text-muted hover:text-ink" aria-label={`Remove ${file.name}`}><X className="size-3.5" aria-hidden /></button></p>
          ) : onFileName && !flagged ? (
            <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-ok"><CheckCircle2 className="size-4" aria-hidden /> On file: {onFileName}. Upload only to replace it.</p>
          ) : null}
          {error && <p className="mt-1.5 text-[12.5px] text-bad" id={`${id}-error`}>{error}</p>}
        </div>
        <div className="flex gap-2">
          <Button type="button" size="sm" onClick={() => pick.current?.click()} aria-describedby={`${id}-label`}><Upload aria-hidden /> Choose file</Button>
          <Button type="button" size="sm" className="sm:hidden" onClick={() => cam.current?.click()} aria-describedby={`${id}-label`}><Camera aria-hidden /> Take photo</Button>
        </div>
      </div>
      <input ref={pick} type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" className="hidden" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
      <input ref={cam} type="file" accept="image/jpeg,image/png" capture="environment" className="hidden" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </div>
  );
}

export default function Portal() {
  const { token = "" } = useParams();
  const [state, setState] = useState<PortalState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [finished, setFinished] = useState(false); // decision made; the link has been closed
  const summaryRef = useRef<HTMLDivElement>(null);
  const submittedRef = useRef(false);
  useEffect(() => { submittedRef.current = submitted; }, [submitted]);

  const load = (initial = false) =>
    api.get<PortalState>(`/api/portal/${token}`, { auth: false }).then((s) => {
      setState(s);
      if (initial) setForm({ ...EMPTY, ...Object.fromEntries(Object.entries(s.prefill).filter(([k]) => k in EMPTY)) });
    }).catch((e: ApiError) => {
      // Once a decision is made the link is revoked. If we just submitted, that means "done", not "invalid".
      if (e.status === 404 && submittedRef.current) setFinished(true);
      else setLoadError(e.message);
    });

  useEffect(() => { load(true); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [token]);
  // After submitting, follow the status until the checks finish.
  useEffect(() => {
    if (!submitted || finished) return;
    const t = setInterval(() => load(), 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitted, finished]);

  const flags = useMemo(() => {
    const m: Record<string, string> = {};
    state?.flags.forEach((f) => { if (f.field && !m[f.field]) m[f.field] = f.message; });
    return m;
  }, [state]);

  const country = (form.country as Country) in COUNTRY ? (form.country as Country) : "IN";
  const c = COUNTRY[country];
  const set = (k: string) => (e: { target: { value: string } }) => {
    const upper = ["pan", "gstin", "tax_id", "bank_code", "postal_code"].includes(k);
    setForm((f) => ({ ...f, [k]: upper ? e.target.value.toUpperCase() : e.target.value }));
    setErrors((er) => { const n = { ...er }; delete n[k]; return n; });
  };

  function validate(): Record<string, string> {
    const e: Record<string, string> = {};
    const req = (k: string, label: string) => { if (!form[k].trim()) e[k] = `Enter your ${label}.`; };
    req("legal_name", "legal name"); req("address_line", "registered address"); req("city", "city"); req("state", "state");
    req("contact_name", "contact name"); req("bank_holder_name", "account holder name"); req("bank_code", c.bank);
    if (!c.postalRe.test(form.postal_code.trim())) e.postal_code = `Enter a valid ${c.postal}.`;
    if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(form.contact_email)) e.contact_email = "Enter a valid email address.";
    if (form.bank_code && !c.bankRe.test(form.bank_code)) e.bank_code = `Enter a valid ${c.bank}, for example ${c.bankEg}.`;
    const hasAccount = form.account_number || state?.prefill.account_on_file;
    if (!hasAccount) e.account_number = "Enter your bank account number.";
    else if (form.account_number && !/^[0-9]{6,18}$/.test(form.account_number)) e.account_number = "Digits only, 6 to 18 of them.";
    if (country === "IN") {
      if (!form.pan && !state?.prefill.pan_on_file) e.pan = "Enter your PAN.";
      else if (form.pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(form.pan)) e.pan = "PAN has 10 characters, like AABCS1234Q.";
      if (!/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(form.gstin)) e.gstin = "GSTIN has 15 characters, like 07AABCS1234Q1Z5.";
    } else if (!form.tax_id) e.tax_id = `Enter your ${c.taxLabel}.`;
    for (const s of SLOTS) {
      if (s.inOnly && country !== "IN") continue;
      const f = files[s.field];
      if (f) {
        if (!ACCEPT.includes(f.type)) e[`doc:${s.slot}`] = "Use a PDF, JPG or PNG file.";
        else if (f.size > (state?.max_file_mb ?? 5) * 1024 * 1024) e[`doc:${s.slot}`] = `This file is larger than ${state?.max_file_mb ?? 5} MB.`;
      } else {
        const onFile = state?.documents_on_file.some((d) => d.slot === s.slot);
        if (!onFile) e[`doc:${s.slot}`] = `Upload your ${s.label.toLowerCase()}.`;
        else if (flags[`doc:${s.slot}`]) e[`doc:${s.slot}`] = flags[`doc:${s.slot}`];
      }
    }
    return e;
  }

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    setSubmitError(null);
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) {
      setSubmitError(`Please fix ${Object.keys(e).length} item${Object.keys(e).length > 1 ? "s" : ""} below before submitting.`);
      summaryRef.current?.focus();
      return;
    }
    const data = new FormData();
    const payload = { ...form };
    if (country !== "IN") { payload.pan = ""; payload.gstin = ""; } else payload.tax_id = "";
    data.set("data", JSON.stringify(payload));
    for (const s of SLOTS) { const f = files[s.field]; if (f && (!s.inOnly || country === "IN")) data.set(s.field, f); }
    setBusy(true);
    try {
      await api.postForm(`/api/portal/${token}/submit`, data);
      setSubmitted(true);
      window.scrollTo({ top: 0 });
      load();
    } catch (err) {
      const ae = err as ApiError;
      setErrors(Object.fromEntries(Object.entries(ae.fields).map(([k, v]) => [k, v])));
      setSubmitError(ae.message);
      summaryRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  const err = (k: string) => errors[k] ?? (submitted ? null : flags[k]) ?? null;
  const inv = (k: string) => ({ "aria-invalid": !!err(k), "aria-describedby": err(k) ? `${k}-error` : undefined });

  const header = (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold">{state?.buyer_name ?? "Vendor registration"}</p>
          <p className="text-xs text-muted">Vendor registration</p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs text-muted"><Lock className="size-3.5" aria-hidden /> Private link</span>
      </div>
    </header>
  );

  if (finished) {
    return (
      <div className="min-h-dvh bg-canvas">{header}
        <main className="mx-auto max-w-2xl px-4 py-10">
          <div className="rounded-lg border border-line bg-surface p-6" aria-live="polite">
            <CheckCircle2 className="mb-3 size-5 text-ok" aria-hidden />
            <h1 className="text-base font-semibold">Your registration has been processed</h1>
            <p className="mt-1 text-[13px] text-muted">We've emailed the outcome to {state?.contact_email ?? "your contact address"}. This link is now closed.</p>
          </div>
        </main>
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="min-h-dvh bg-canvas">{header}
        <main className="mx-auto max-w-2xl px-4 py-12"><div role="alert" className="rounded-lg border border-line bg-surface p-6">
          <AlertCircle className="mb-3 size-5 text-bad" aria-hidden /><h1 className="text-base font-semibold">This link can't be used</h1>
          <p className="mt-1 text-[13px] text-muted">{loadError}</p></div></main>
      </div>
    );
  }
  if (!state) {
    return <div className="min-h-dvh bg-canvas">{header}<main className="mx-auto max-w-2xl px-4 py-8"><Skeleton className="mb-3 h-6 w-64" /><Skeleton className="mb-8 w-80" /><Skeleton className="mb-3 h-9" /><Skeleton className="mb-3 h-9" /><Skeleton className="h-9" /></main></div>;
  }

  if (!state.can_submit || submitted) {
    const processing = ["SUBMITTED", "PROCESSING"].includes(state.status);
    return (
      <div className="min-h-dvh bg-canvas">{header}
        <main className="mx-auto max-w-2xl px-4 py-10">
          <div className="rounded-lg border border-line bg-surface p-6" aria-live="polite">
            {processing ? <Spinner className="mb-3 size-5 text-accent" /> : <CheckCircle2 className="mb-3 size-5 text-ok" aria-hidden />}
            <h1 className="text-base font-semibold">{processing ? "Thanks, we're checking your details" : state.status === "PENDING_VENDOR" ? "We need a few more things" : "Registration received"}</h1>
            <p className="mt-1 text-[13px] text-muted">
              {processing ? "This usually takes under a minute. You can keep this page open or close it; we'll also email you."
                : state.status === "PENDING_VENDOR" ? "We've emailed you a list. Reload this page to update only those items."
                : state.status === "PENDING_INTERNAL" ? "Your registration is with our procurement team for a final review. You don't need to do anything right now."
                : "Status: " + state.status_label + "."}
            </p>
            {state.status === "PENDING_VENDOR" && <Button className="mt-4" variant="primary" onClick={() => { setSubmitted(false); load(true); }}>Update my registration</Button>}
          </div>
        </main>
      </div>
    );
  }

  const isResubmit = state.attempt_no > 1;
  return (
    <div className="min-h-dvh bg-canvas">
      {header}
      <main className="mx-auto max-w-2xl px-4 py-6 sm:py-8">
        <h1 className="text-xl font-semibold tracking-[-0.01em]">{isResubmit ? "Update your registration" : `Register ${state.company} as a vendor`}</h1>
        <p className="mt-1 text-[13px] text-muted">
          {isResubmit ? `Attempt ${state.attempt_no} of ${state.max_attempts}. Only the highlighted items need changing; everything else is saved.`
            : `${state.buyer_name} needs your company, tax and bank details to set you up for payments. It takes about 5 minutes.`}
        </p>

        {state.flags.length > 0 && (
          <div className="mt-5 rounded-lg border border-warn/25 bg-warn-soft p-4">
            <p className="text-[13px] font-semibold text-warn">Please fix {state.flags.length === 1 ? "this item" : `these ${state.flags.length} items`}</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] text-ink-2">{state.flags.map((f, i) => <li key={i}>{f.message}</li>)}</ul>
          </div>
        )}

        <div ref={summaryRef} tabIndex={-1} aria-live="assertive" className="outline-none">
          {submitError && <p role="alert" className="mt-5 rounded-md border border-bad/20 bg-bad-soft px-3 py-2 text-[13px] text-bad">{submitError}</p>}
        </div>

        <form onSubmit={submit} noValidate className="mt-6 rounded-lg border border-line bg-surface p-4 sm:p-6">
          <Section title="Company" description="As registered with the tax authorities.">
            <Field id="legal_name" label="Legal name" error={err("legal_name")} className="sm:col-span-2" hint="Exactly as on your GST certificate, e.g. ending in Pvt Ltd or LLP.">
              <Input id="legal_name" value={form.legal_name} onChange={set("legal_name")} autoComplete="organization" {...inv("legal_name")} />
            </Field>
            <Field id="trade_name" label="Trade name" optional error={err("trade_name")}>
              <Input id="trade_name" value={form.trade_name} onChange={set("trade_name")} {...inv("trade_name")} />
            </Field>
            <Field id="country" label="Country of registration" error={err("country")}>
              <Select id="country" value={form.country} onChange={set("country")} {...inv("country")}>
                {Object.entries(COUNTRY).map(([k, v]) => <option key={k} value={k}>{v.name}</option>)}
              </Select>
            </Field>
            <Field id="address_line" label="Registered address" error={err("address_line")} className="sm:col-span-2">
              <Textarea id="address_line" rows={2} value={form.address_line} onChange={set("address_line")} autoComplete="street-address" {...inv("address_line")} />
            </Field>
            <Field id="city" label="City" error={err("city")}>
              <Input id="city" value={form.city} onChange={set("city")} autoComplete="address-level2" {...inv("city")} />
            </Field>
            <Field id="state" label={country === "IN" ? "State / UT" : "State / county"} error={err("state")}>
              {country === "IN" ? (
                <Select id="state" value={form.state} onChange={set("state")} {...inv("state")}>
                  <option value="">Select…</option>{IN_STATES.map((s) => <option key={s}>{s}</option>)}
                </Select>
              ) : <Input id="state" value={form.state} onChange={set("state")} autoComplete="address-level1" {...inv("state")} />}
            </Field>
            <Field id="postal_code" label={c.postal} error={err("postal_code")}>
              <Input id="postal_code" value={form.postal_code} onChange={set("postal_code")} inputMode={country === "GB" ? "text" : "numeric"} autoComplete="postal-code" className="num" {...inv("postal_code")} />
            </Field>
          </Section>

          <Section title="Contact" description="Who we should contact about this registration and payments.">
            <Field id="contact_name" label="Full name" error={err("contact_name")}>
              <Input id="contact_name" value={form.contact_name} onChange={set("contact_name")} autoComplete="name" {...inv("contact_name")} />
            </Field>
            <Field id="contact_email" label="Email" error={err("contact_email")}>
              <Input id="contact_email" type="email" value={form.contact_email} onChange={set("contact_email")} autoComplete="email" {...inv("contact_email")} />
            </Field>
            <Field id="contact_phone" label="Phone" optional error={err("contact_phone")}>
              <Input id="contact_phone" type="tel" value={form.contact_phone} onChange={set("contact_phone")} autoComplete="tel" {...inv("contact_phone")} />
            </Field>
          </Section>

          <Section title="Tax registration">
            {country === "IN" ? (
              <>
                <Field id="pan" label="PAN" error={err("pan")} hint={state.prefill.pan_on_file && !form.pan ? `On file (${state.prefill.pan_on_file}). Leave blank to keep it.` : "10 characters, e.g. AABCS1234Q"}>
                  <Input id="pan" value={form.pan} onChange={set("pan")} maxLength={10} autoCapitalize="characters" className="num font-mono" placeholder={state.prefill.pan_on_file ? `•••••• ${state.prefill.pan_on_file.slice(-4)}` : ""} {...inv("pan")} />
                </Field>
                <Field id="gstin" label="GSTIN" error={err("gstin")} hint="15 characters, e.g. 07AABCS1234Q1Z5">
                  <Input id="gstin" value={form.gstin} onChange={set("gstin")} maxLength={15} autoCapitalize="characters" className="num font-mono" {...inv("gstin")} />
                </Field>
              </>
            ) : (
              <Field id="tax_id" label={c.taxLabel} error={err("tax_id")} hint={country === "US" ? "Format 12-3456789" : "Format GB123456789"}>
                <Input id="tax_id" value={form.tax_id} onChange={set("tax_id")} autoCapitalize="characters" className="num font-mono" {...inv("tax_id")} />
              </Field>
            )}
          </Section>

          <Section title="Bank account" description="Payments will only ever be made to this account. It must be in your company's name.">
            <Field id="bank_holder_name" label="Account holder name" error={err("bank_holder_name")} className="sm:col-span-2">
              <Input id="bank_holder_name" value={form.bank_holder_name} onChange={set("bank_holder_name")} {...inv("bank_holder_name")} />
            </Field>
            <Field id="account_number" label="Account number" error={err("account_number")} hint={state.prefill.account_on_file && !form.account_number ? `On file (${state.prefill.account_on_file}). Leave blank to keep it.` : undefined}>
              <Input id="account_number" value={form.account_number} onChange={set("account_number")} inputMode="numeric" autoComplete="off" className="num font-mono" placeholder={state.prefill.account_on_file ? `•••• ${state.prefill.account_on_file.slice(-4)}` : ""} {...inv("account_number")} />
            </Field>
            <Field id="bank_code" label={c.bank} error={err("bank_code")} hint={`e.g. ${c.bankEg}`}>
              <Input id="bank_code" value={form.bank_code} onChange={set("bank_code")} autoCapitalize="characters" className="num font-mono" {...inv("bank_code")} />
            </Field>
          </Section>

          <Section title="Documents" description="Clear scans or photos. On a phone you can take a photo directly.">
            {SLOTS.filter((s) => !s.inOnly || country === "IN").map((s) => (
              <FileField key={s.slot} label={s.label} hint={s.hint} file={files[s.field] ?? null} maxMb={state.max_file_mb}
                onFile={(f) => { setFiles({ ...files, [s.field]: f }); setErrors((er) => { const n = { ...er }; delete n[`doc:${s.slot}`]; return n; }); }}
                onFileError={errors[`doc:${s.slot}`] ?? null}
                flagged={files[s.field] ? null : flags[`doc:${s.slot}`] ?? null}
                onFileName={state.documents_on_file.find((d) => d.slot === s.slot)?.name ?? null} />
            ))}
          </Section>

          <div className="flex flex-col-reverse items-stretch gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted">Your PAN and bank account number are encrypted and only visible to authorised {state.buyer_name} staff.</p>
            <Button type="submit" variant="primary" disabled={busy} className="h-10 sm:h-9">{busy && <Spinner />}{isResubmit ? "Resubmit" : "Submit registration"}</Button>
          </div>
        </form>
        {state.last_submitted_at && <p className="mt-4 text-center text-xs text-muted">Last submitted {fmtDateTime(state.last_submitted_at)}</p>}
      </main>
    </div>
  );
}
