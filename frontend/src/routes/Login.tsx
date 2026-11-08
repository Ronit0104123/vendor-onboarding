import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Lock } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";

export default function Login() {
  const { me, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (me) return <Navigate to={from} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-canvas px-4">
      <main className="m-auto w-full max-w-[360px] py-10">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-md bg-accent text-white">
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
          </div>
          <span className="text-sm font-semibold">Vendor Onboarding</span>
        </div>
        <h1 className="text-xl font-semibold tracking-[-0.01em]">Sign in to procurement</h1>
        <p className="mt-1 text-[13px] text-muted">Review vendor registrations, checks and decisions.</p>
        <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
          <Field id="email" label="Work email">
            <Input id="email" type="email" autoComplete="username" required value={email}
              onChange={(e) => setEmail(e.target.value)} aria-invalid={!!error} autoFocus />
          </Field>
          <Field id="password" label="Password">
            <Input id="password" type="password" autoComplete="current-password" required value={password}
              onChange={(e) => setPassword(e.target.value)} aria-invalid={!!error} />
          </Field>
          <div aria-live="polite" className="min-h-5 text-[13px] text-bad">{error}</div>
          <Button variant="primary" type="submit" disabled={busy || !email || !password}>
            {busy ? <Spinner /> : <Lock aria-hidden />} Sign in
          </Button>
        </form>
        <p className="mt-8 text-xs text-muted">Sessions end after 30 minutes of inactivity. Repeated failed attempts temporarily lock the account.</p>
      </main>
    </div>
  );
}
