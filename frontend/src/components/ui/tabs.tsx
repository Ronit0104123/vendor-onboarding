import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Accessible tabs: arrow keys move between tabs, only the active tab is in the tab order. */
export function Tabs({ tabs, value, onChange, label }: {
  tabs: { key: string; label: ReactNode }[]; value: string; onChange: (k: string) => void; label: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (i + dir + tabs.length) % tabs.length;
    onChange(tabs[next].key);
    refs.current[next]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-line px-2">
      {tabs.map((t, i) => (
        <button key={t.key} ref={(el) => { refs.current[i] = el; }} role="tab" id={`tab-${t.key}`} aria-selected={value === t.key}
          aria-controls={`panel-${t.key}`} tabIndex={value === t.key ? 0 : -1} onClick={() => onChange(t.key)} onKeyDown={(e) => onKey(e, i)}
          className={cn("-mb-px whitespace-nowrap border-b-2 px-2.5 py-2.5 text-[13px] font-medium transition-colors duration-150",
            value === t.key ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink")}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, active, children }: { id: string; active: boolean; children: ReactNode }) {
  if (!active) return null;
  return <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={0} className="focus-visible:outline-offset-[-2px]">{children}</div>;
}
