// Small shared pieces for the catalog components: brand card, pill buttons, inputs, money.

import type { ReactNode } from "react";

import { accents } from "@/lib/catalog-schema";

export type Accent = (typeof accents)[number];

/** Static class names so Tailwind generates them (one accent per card). */
export const ACCENT_BAR: Record<Accent, string> = {
  teal: "bg-accent-teal",
  leaf: "bg-accent-leaf",
  sun: "bg-accent-sun",
  sky: "bg-accent-sky",
  coral: "bg-accent-coral",
};

export function Card({ accent, children, wide = false, fluid = false, label }: {
  accent?: Accent;
  children: ReactNode;
  wide?: boolean;
  /** Fill a grid cell (tour cards side by side on wider screens). */
  fluid?: boolean;
  label?: string;
}) {
  const width = fluid ? "flex h-full flex-col" : wide ? "max-w-md" : "max-w-card";
  return (
    <section
      aria-label={label}
      className={`w-full overflow-hidden rounded-card border border-line bg-surface ${width}`}
    >
      {accent && <div aria-hidden className={`h-1.5 ${ACCENT_BAR[accent]}`} />}
      <div className={`flex flex-col gap-2.5 p-4 ${fluid ? "flex-1" : ""}`}>{children}</div>
    </section>
  );
}

export function Pill({ children, onClick, type = "button", disabled, variant = "primary" }: {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  variant?: "primary" | "outline";
}) {
  const look =
    variant === "primary"
      ? "bg-brand-orange text-ink hover:opacity-90"
      : "border border-line text-ink hover:border-brand-orange";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`min-h-11 rounded-button px-4 py-2 text-brand-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-orange disabled:cursor-not-allowed disabled:opacity-50 ${look}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, hint, error, className = "", ...input }: React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  /** Shown under the input in place of the hint; marks the input invalid. */
  error?: string | null;
}) {
  const id = input.id ?? input.name;
  return (
    <label className={`flex min-w-0 flex-col gap-1 text-brand-sm ${className}`}>
      <span className="font-semibold">{label}</span>
      <input
        {...input}
        aria-invalid={error ? true : undefined}
        aria-describedby={error && id ? `${id}-error` : undefined}
        className={`min-h-11 w-full min-w-0 rounded-input border px-3 py-2 text-brand-md outline-none focus:border-brand-orange ${error ? "border-accent-coral" : "border-line"}`}
      />
      {error ? (
        <span id={id ? `${id}-error` : undefined} className="text-brand-xs font-semibold text-accent-coral">
          {error}
        </span>
      ) : (
        hint && <span className="text-brand-xs text-muted">{hint}</span>
      )}
    </label>
  );
}

export const usd = (n: number) => `USD ${n.toLocaleString("en-US")}`;

export function niceDate(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}
