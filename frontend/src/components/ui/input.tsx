import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const field =
  "w-full rounded-md border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-muted/80 transition-colors duration-150 hover:border-[#c4c2bc] focus:border-accent focus:outline-none focus-visible:outline-none focus:ring-2 focus:ring-accent/20 disabled:bg-subtle disabled:text-muted aria-[invalid=true]:border-bad aria-[invalid=true]:ring-bad/15";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn(field, "h-9", className)} {...p} />
));
Input.displayName = "Input";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(({ className, ...p }, ref) => (
  <select ref={ref} className={cn(field, "h-9 appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%2366645f%22 stroke-width=%222%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[length:12px] bg-[right_10px_center] bg-no-repeat pr-8", className)} {...p} />
));
Select.displayName = "Select";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn(field, "min-h-20 py-2", className)} {...p} />
));
Textarea.displayName = "Textarea";

export function Field({ id, label, hint, error, children, className, optional }: {
  id: string; label: string; hint?: ReactNode; error?: string | null; children: ReactNode; className?: string; optional?: boolean;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-[13px] font-medium text-ink-2">
        {label}
        {optional && <span className="ml-1 font-normal text-muted">(optional)</span>}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-[12.5px] text-bad">{error}</p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-[12.5px] text-muted">{hint}</p>
      ) : null}
    </div>
  );
}
