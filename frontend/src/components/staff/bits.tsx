import type { Status } from "@/lib/staff-api";
import { flagLabel } from "@/lib/staff-api";

const STATUS_LOOK: Record<Status, string> = {
  new: "bg-accent-sky/25 text-ink",
  contacted: "bg-accent-sun/30 text-ink",
  pending: "bg-accent-teal/20 text-ink",
  confirmed: "bg-accent-leaf/30 text-ink",
  closed: "bg-line text-muted",
};

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-brand-xs font-semibold capitalize ${STATUS_LOOK[status]}`}>
      {status}
    </span>
  );
}

/** Flags that need a person are coral; information-only ones are grey. */
export function FlagChips({ flags, info }: { flags: string[]; info?: Set<string> }) {
  if (!flags.length) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {flags.map((f) => (
        <span
          key={f}
          className={`rounded-full px-2 py-0.5 text-brand-xs font-semibold ${
            info?.has(f) ? "bg-line text-muted" : "bg-accent-coral/15 text-accent-coral"
          }`}
        >
          {flagLabel(f)}
        </span>
      ))}
    </span>
  );
}

export const INFO_FLAGS = new Set(["direct_quote", "from_traveller"]);

export function Panel({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="rounded-card border border-line bg-surface p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-brand-md font-bold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
