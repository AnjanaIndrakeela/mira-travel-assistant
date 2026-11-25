// Small shared pieces for the catalog components: brand card, pill buttons, inputs, icons, money.
// Only brand tokens (brand.css) are used; depth comes from soft shadows and accent tints.

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

/** The accent as a soft tint behind an icon (the icon itself takes the accent colour). */
export const ACCENT_SOFT: Record<Accent, string> = {
  teal: "bg-accent-teal/10 text-accent-teal",
  leaf: "bg-accent-leaf/12 text-accent-leaf",
  sun: "bg-accent-sun/20 text-ink",
  sky: "bg-accent-sky/10 text-accent-sky",
  coral: "bg-accent-coral/10 text-accent-coral",
};

/** Accent text for decorative marks only (bullets, small icons). */
export const ACCENT_TEXT: Record<Accent, string> = {
  teal: "text-accent-teal",
  leaf: "text-accent-leaf",
  sun: "text-accent-sun",
  sky: "text-accent-sky",
  coral: "text-accent-coral",
};

/** A soft, layered shadow: cards float a little off the chat instead of sitting in boxes. */
export const SHADOW = "shadow-[0_1px_2px_rgba(17,17,17,0.05),0_10px_28px_-14px_rgba(17,17,17,0.22)]";

const ICONS = {
  clock: <><circle cx="8" cy="8" r="6.25" /><path d="M8 4.75V8l2.25 1.5" /></>,
  calendar: <><rect x="2.25" y="3.25" width="11.5" height="10.5" rx="2" /><path d="M2.25 6.75h11.5M5.5 1.75v3M10.5 1.75v3" /></>,
  users: <><circle cx="6" cy="5.25" r="2.5" /><path d="M1.75 13.5c0-2.4 1.9-4 4.25-4s4.25 1.6 4.25 4" /><path d="M10.5 3a2.4 2.4 0 0 1 0 4.6M12 9.75c1.3.5 2.25 1.75 2.25 3.75" /></>,
  user: <><circle cx="8" cy="5" r="2.75" /><path d="M2.75 14c0-2.9 2.35-4.75 5.25-4.75s5.25 1.85 5.25 4.75" /></>,
  route: <><circle cx="3.75" cy="12.25" r="1.75" /><circle cx="12.25" cy="3.75" r="1.75" /><path d="M5.5 12.25h4.25a2.25 2.25 0 0 0 0-4.5h-3.5a2.25 2.25 0 0 1 0-4.5h4.25" /></>,
  sparkle: <path d="M8 1.75 9.4 6.6l4.85 1.4-4.85 1.4L8 14.25 6.6 9.4 1.75 8l4.85-1.4z" />,
  check: <path d="m3.25 8.5 3 3 6.5-7" />,
  tag: <><path d="M8.6 1.75H13.5a.75.75 0 0 1 .75.75V7.4L7.9 13.75a1 1 0 0 1-1.4 0L2.25 9.5a1 1 0 0 1 0-1.4z" /><circle cx="10.9" cy="5.1" r="1.1" /></>,
  card: <><rect x="1.75" y="3.25" width="12.5" height="9.5" rx="1.75" /><path d="M1.75 6.5h12.5M4.5 10h2.5" /></>,
  chat: <path d="M2.25 3.75a1.5 1.5 0 0 1 1.5-1.5h8.5a1.5 1.5 0 0 1 1.5 1.5v6a1.5 1.5 0 0 1-1.5 1.5H6.5l-3 2.5v-2.5h.25a1.5 1.5 0 0 1-1.5-1.5z" />,
  shield: <><path d="M8 1.75 13.25 3.5v4c0 3.1-2.2 5.5-5.25 6.75C4.95 13 2.75 10.6 2.75 7.5v-4z" /><path d="m5.75 8 1.5 1.5 3-3" /></>,
  book: <><path d="M2.25 3c1.9-.6 3.9-.4 5.75.75 1.85-1.15 3.85-1.35 5.75-.75v10c-1.9-.6-3.9-.4-5.75.75C6.15 12.6 4.15 12.4 2.25 13z" /><path d="M8 3.75v10" /></>,
  meal: <><path d="M4.5 1.75v12.5M2.75 1.75v3.5a1.75 1.75 0 0 0 3.5 0v-3.5" /><path d="M11.5 14.25V1.75c-1.6.6-2.5 2.3-2.5 4.5v3h2.5" /></>,
  bed: <><path d="M1.75 12.75v-8.5M1.75 9.75h12.5v3M14.25 9.75V8.5a2 2 0 0 0-2-2H7.5v3.25" /><circle cx="4.5" cy="7.75" r="1.25" /></>,
  photo: <><rect x="1.75" y="2.75" width="12.5" height="10.5" rx="1.75" /><circle cx="5.5" cy="6.25" r="1.25" /><path d="m14.25 10.5-3.5-3.5-7 6.25" /></>,
  arrow: <path d="M3 8h10M9 4l4 4-4 4" />,
  chevron: <path d="m4 6 4 4 4-4" />,
} as const;

export type IconName = keyof typeof ICONS;

/** A 16px line icon in the current text colour (decorative: always aria-hidden). */
export function Icon({ name, className = "h-4 w-4" }: { name: IconName; className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
    >
      {ICONS[name]}
    </svg>
  );
}

/** An icon in a soft accent-tinted circle: the visual anchor of a card's header. */
export function IconBadge({ name, accent, size = "md" }: { name: IconName; accent?: Accent; size?: "sm" | "md" }) {
  const tone = accent ? ACCENT_SOFT[accent] : "bg-brand-orange/10 text-brand-orange";
  const box = size === "sm" ? "h-7 w-7" : "h-9 w-9";
  return (
    <span aria-hidden className={`flex shrink-0 items-center justify-center rounded-full ${box} ${tone}`}>
      <Icon name={name} className={size === "sm" ? "h-3.5 w-3.5" : "h-[18px] w-[18px]"} />
    </span>
  );
}

/** A small rounded label: tour length, "Bookable online", a meal, a source. */
export function Chip({ children, icon, tone = "plain", className = "" }: {
  children: ReactNode;
  icon?: IconName;
  tone?: "plain" | "glass" | "orange" | Accent;
  className?: string;
}) {
  const look =
    tone === "glass"
      ? "bg-surface/90 text-ink shadow-sm backdrop-blur"
      : tone === "orange"
        ? "bg-brand-orange/10 text-ink"
        : tone === "plain"
          ? "bg-ink/[0.04] text-muted"
          : ACCENT_SOFT[tone];
  return (
    <span className={`inline-flex max-w-full items-center gap-1 rounded-button px-2.5 py-1 text-brand-xs font-medium ${look} ${className}`}>
      {icon && <Icon name={icon} className="h-3.5 w-3.5" />}
      <span className="truncate">{children}</span>
    </span>
  );
}

export function Card({ accent, children, wide = false, fluid = false, label, title, subtitle, icon }: {
  accent?: Accent;
  children: ReactNode;
  wide?: boolean;
  /** Fill a grid cell (tour cards side by side on wider screens). */
  fluid?: boolean;
  label?: string;
  /** A header row: an accent-tinted icon, the title and an optional line under it. */
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: IconName;
}) {
  const width = fluid ? "flex h-full flex-col" : wide ? "max-w-md" : "max-w-card";
  return (
    <section
      aria-label={label}
      className={`relative w-full overflow-hidden rounded-card border border-line/80 bg-surface ${SHADOW} ${width}`}
    >
      {accent && (
        <div aria-hidden className={`absolute inset-x-0 top-0 h-1 ${ACCENT_BAR[accent]}`} />
      )}
      <div className={`flex flex-col gap-3 p-4 ${accent ? "pt-5" : ""} ${fluid ? "flex-1" : ""}`}>
        {title && (
          <div className="flex items-center gap-3">
            {icon && <IconBadge name={icon} accent={accent} />}
            <div className="min-w-0">
              <h3 className="text-brand-md font-semibold leading-snug">{title}</h3>
              {subtitle && <p className="text-brand-xs text-muted">{subtitle}</p>}
            </div>
          </div>
        )}
        {children}
      </div>
    </section>
  );
}

export function Pill({ children, onClick, type = "button", disabled, variant = "primary", icon }: {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  variant?: "primary" | "outline";
  /** A trailing icon (an arrow for "go on", say). */
  icon?: IconName;
}) {
  const look =
    variant === "primary"
      ? "bg-brand-orange text-ink shadow-[0_6px_16px_-8px_rgba(242,107,29,0.9)] hover:-translate-y-px hover:shadow-[0_10px_20px_-10px_rgba(242,107,29,0.95)]"
      : "border border-line bg-surface text-ink hover:border-ink/40 hover:bg-ink/[0.03]";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`group/pill inline-flex min-h-11 items-center justify-center gap-1.5 rounded-button px-5 py-2 text-brand-sm font-semibold transition-all active:translate-y-0 active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-orange disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none ${look}`}
    >
      {children}
      {icon && <Icon name={icon} className="h-4 w-4 transition-transform group-hover/pill:translate-x-0.5" />}
    </button>
  );
}

/** Input styling shared by fields, text areas and selects. */
export const INPUT =
  "w-full min-w-0 rounded-input border bg-surface px-3 py-2 text-brand-md outline-none transition-shadow placeholder:text-muted/60 hover:border-ink/30 focus:border-brand-orange focus:ring-4 focus:ring-brand-orange/15";

export function Field({ label, hint, error, className = "", ...input }: React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  /** Shown under the input in place of the hint; marks the input invalid. */
  error?: string | null;
}) {
  const id = input.id ?? input.name;
  return (
    <label className={`flex min-w-0 flex-col gap-1.5 text-brand-sm ${className}`}>
      <span className="font-medium text-ink/80">{label}</span>
      <input
        {...input}
        aria-invalid={error ? true : undefined}
        aria-describedby={error && id ? `${id}-error` : undefined}
        className={`min-h-11 ${INPUT} ${error ? "border-accent-coral focus:border-accent-coral focus:ring-accent-coral/15" : "border-line"}`}
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

/** "3 May 2027" (short month, for compact chips). */
export function shortDate(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
