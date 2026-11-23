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

export function Card({ accent, children, wide = false, label }: {
  accent?: Accent;
  children: ReactNode;
  wide?: boolean;
  label?: string;
}) {
  return (
    <section
      aria-label={label}
      className={`w-full overflow-hidden rounded-card border border-line bg-surface ${wide ? "max-w-md" : "max-w-card"}`}
    >
      {accent && <div aria-hidden className={`h-1.5 ${ACCENT_BAR[accent]}`} />}
      <div className="flex flex-col gap-2.5 p-4">{children}</div>
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
      className={`min-h-10 rounded-button px-4 py-2 text-brand-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-orange disabled:cursor-not-allowed disabled:opacity-50 ${look}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, hint, ...input }: React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-brand-sm">
      <span className="font-semibold">{label}</span>
      <input
        {...input}
        className="min-h-10 rounded-input border border-line px-3 py-2 text-brand-md outline-none focus:border-brand-orange"
      />
      {hint && <span className="text-brand-xs text-muted">{hint}</span>}
    </label>
  );
}

export const usd = (n: number) => `USD ${n.toLocaleString("en-US")}`;

export function niceDate(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}
