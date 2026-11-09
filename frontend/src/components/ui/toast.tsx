import { useEffect } from "react";
import { CheckCircle2, X } from "lucide-react";

export interface ToastMessage { id: number; title: string; body?: string }

/** A single success toast, bottom-right. Announced to screen readers; auto-dismisses after 5 s. */
export function Toast({ toast, onDismiss }: { toast: ToastMessage | null; onDismiss: () => void }) {
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(onDismiss, 5000);
    return () => clearTimeout(t);
  }, [toast, onDismiss]);

  return (
    <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex justify-end sm:inset-x-auto sm:right-6 sm:bottom-6">
      {toast && (
        <div key={toast.id} className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border border-ok/20 bg-surface p-3.5 shadow-[0_8px_24px_rgba(0,0,0,0.08)]">
          <CheckCircle2 className="mt-0.5 size-[18px] shrink-0 text-ok" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-semibold text-ink">{toast.title}</p>
            {toast.body && <p className="mt-0.5 text-[13px] text-muted">{toast.body}</p>}
          </div>
          <button onClick={onDismiss} className="rounded p-0.5 text-muted hover:bg-hover hover:text-ink" aria-label="Dismiss">
            <X className="size-4" aria-hidden />
          </button>
        </div>
      )}
    </div>
  );
}
