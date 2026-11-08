import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Activity, FlaskConical, LayoutList, LogOut, Mail, Menu, X } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Button } from "./ui/button";

const NAV = [
  { to: "/", label: "Vendors", icon: LayoutList, end: true },
  { to: "/runs", label: "Pipeline runs", icon: Activity },
  { to: "/outbox", label: "Outbox", icon: Mail },
  { to: "/demo", label: "Demo scenarios", icon: FlaskConical },
];

function Brand() {
  const { me } = useAuth();
  return (
    <div className="flex items-center gap-2.5 px-3 py-4">
      <div className="flex size-7 items-center justify-center rounded-md bg-accent text-white">
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
      </div>
      <div className="min-w-0 leading-tight">
        <p className="text-[13px] font-semibold text-ink">Vendor Onboarding</p>
        <p className="truncate text-xs text-muted">{me?.buyer_name}</p>
      </div>
    </div>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5 px-2">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate}
          className={({ isActive }) => cn(
            "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors duration-150",
            isActive ? "bg-surface text-ink shadow-[0_0_0_1px_var(--color-line)]" : "text-ink-2 hover:bg-hover hover:text-ink",
          )}>
          <Icon className="size-4 text-muted" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function UserBox() {
  const { me, logout } = useAuth();
  if (!me) return null;
  return (
    <div className="mt-auto border-t border-line p-3">
      <div className="flex items-center gap-2.5">
        <div className="flex size-7 items-center justify-center rounded-full bg-ink text-[11px] font-semibold text-white" aria-hidden>
          {me.name.split(" ").map((p) => p[0]).join("").slice(0, 2)}
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-[13px] font-medium">{me.name}</p>
          <p className="text-xs text-muted">{me.role === "ADMIN" ? "Admin" : "Viewer"}</p>
        </div>
        <Button variant="ghost" size="icon" onClick={() => logout()} aria-label="Sign out" title="Sign out"><LogOut aria-hidden /></Button>
      </div>
      <button onClick={() => logout(true)} className="mt-2 text-xs text-muted underline-offset-2 hover:text-ink hover:underline">
        Sign out of all devices
      </button>
    </div>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[232px_1fr]">
      <a href="#main" className="sr-only-focusable fixed left-2 top-2 z-50 rounded bg-surface px-3 py-2 text-sm">Skip to content</a>
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-line bg-canvas lg:flex">
        <Brand />
        <Nav />
        <UserBox />
      </aside>

      <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b border-line bg-canvas/95 px-3 backdrop-blur lg:hidden">
        <Button variant="ghost" size="icon" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open}><Menu aria-hidden /></Button>
        <span className="text-[13px] font-semibold">Vendor Onboarding</span>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-ink/25" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-line bg-canvas">
            <div className="flex items-center justify-between pr-2"><Brand />
              <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="Close menu" autoFocus><X aria-hidden /></Button>
            </div>
            <Nav onNavigate={() => setOpen(false)} />
            <UserBox />
          </div>
        </div>
      )}

      <main id="main" className="min-w-0">
        <Outlet />
      </main>
    </div>
  );
}

export function Page({ title, description, actions, children, breadcrumb }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode; breadcrumb?: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
      {breadcrumb && <div className="mb-2 text-[13px] text-muted">{breadcrumb}</div>}
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[19px] font-semibold tracking-[-0.01em] text-ink">{title}</h1>
          {description && <div className="mt-1 text-[13px] text-muted">{description}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

