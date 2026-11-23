import type { ComponentOf } from "@/lib/catalog-schema";

/** Which of our published pages the answer used ([1], [2], ...). */
export function SourceList({ items }: ComponentOf<"source_list">) {
  return (
    <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
      {items.map((s) => (
        <li
          key={s.n}
          title={`${s.title} – ${s.section}`}
          className="max-w-full truncate rounded-button border border-line bg-surface px-2.5 py-1 text-brand-xs text-muted"
        >
          <span className="font-semibold text-ink">[{s.n}]</span> {s.title}
          {s.section && s.section !== "Overview" ? ` – ${s.section}` : ""}
        </li>
      ))}
    </ul>
  );
}
