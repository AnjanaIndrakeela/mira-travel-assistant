import type { ComponentOf } from "@/lib/catalog-schema";

/** Which of our published pages the answer used ([1], [2], ...). */
export function SourceList({ items }: ComponentOf<"source_list">) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Sources</p>
      <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
        {items.map((s) => (
          <li
            key={s.n}
            title={`${s.title} – ${s.section}`}
            className="inline-flex max-w-full items-center gap-1.5 rounded-button border border-line/80 bg-surface py-1 pl-1 pr-3 text-brand-xs text-muted shadow-sm"
          >
            <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-ink px-1 text-[11px] font-bold text-brand-white">{s.n}</span>
            <span className="truncate">
              <span className="font-medium text-ink">{s.title}</span>
              {s.section && s.section !== "Overview" ? ` · ${s.section}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
