import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Check, Copy } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { VendorRow } from "@/lib/types";
import { Dialog } from "./ui/dialog";
import { Button } from "./ui/button";
import { Field, Input, Select } from "./ui/input";
import { Spinner } from "./ui/misc";

const CATEGORIES = ["Hardware", "Raw materials", "Logistics", "Packaging", "Services", "IT", "Other"];

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button size="sm" type="button" onClick={async () => {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    }}>
      {done ? <Check aria-hidden /> : <Copy aria-hidden />}
      <span aria-live="polite">{done ? "Copied" : label}</span>
    </Button>
  );
}

export function NewVendorDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const { me } = useAuth();
  const [form, setForm] = useState({ display_name: "", category: "Hardware", contact_email: "", requested_by: me?.name ?? "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ vendor: VendorRow; portal_url: string } | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      setCreated(await api.post("/api/vendors", form));
      onCreated();
    } catch (err) {
      const ae = err as ApiError;
      setErrors(Object.keys(ae.fields).length ? ae.fields : { _: ae.message });
    } finally {
      setBusy(false);
    }
  }

  function close() {
    setCreated(null);
    setForm({ display_name: "", category: "Hardware", contact_email: "", requested_by: me?.name ?? "" });
    onClose();
  }

  if (created) {
    return (
      <Dialog open={open} onClose={close} title="Invitation sent"
        description={`${created.vendor.display_name} (${created.vendor.ref}) has been invited. The email is in the outbox.`}
        footer={<><Link to={`/vendors/${created.vendor.id}`} onClick={close}><Button>Open vendor</Button></Link><Button variant="primary" onClick={close}>Done</Button></>}>
        <p className="mb-2 text-[13px] font-medium text-ink-2">Vendor portal link</p>
        <div className="flex items-center gap-2 rounded-md border border-line bg-subtle p-2">
          <code className="num min-w-0 flex-1 truncate font-mono text-xs">{created.portal_url}</code>
          <CopyButton text={created.portal_url} />
        </div>
        <p className="mt-2 text-xs text-muted">Personal to this vendor. Expires in 14 days and stops working once a decision is made.</p>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onClose={close} title="New vendor request"
      description="The vendor gets a private link to submit their details and documents."
      footer={<><Button onClick={close}>Cancel</Button><Button variant="primary" type="submit" form="new-vendor" disabled={busy}>{busy && <Spinner />}Create and send invite</Button></>}>
      <form id="new-vendor" onSubmit={submit} className="grid gap-4" noValidate>
        <Field id="display_name" label="Vendor name" error={errors.display_name}>
          <Input id="display_name" required value={form.display_name} onChange={set("display_name")} placeholder="e.g. Sharma Hardware Pvt Ltd" aria-invalid={!!errors.display_name} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="category" label="Category">
            <Select id="category" value={form.category} onChange={set("category")}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select>
          </Field>
          <Field id="requested_by" label="Requested by" error={errors.requested_by}>
            <Input id="requested_by" value={form.requested_by} onChange={set("requested_by")} aria-invalid={!!errors.requested_by} />
          </Field>
        </div>
        <Field id="contact_email" label="Vendor contact email" error={errors.contact_email}>
          <Input id="contact_email" type="email" value={form.contact_email} onChange={set("contact_email")} placeholder="accounts@vendor.example" aria-invalid={!!errors.contact_email} />
        </Field>
        {errors._ && <p role="alert" className="text-[13px] text-bad">{errors._}</p>}
      </form>
    </Dialog>
  );
}
