import type { ComponentOf } from "@/lib/catalog-schema";

type Day = ComponentOf<"itinerary_day">;

/** A tour's published day-by-day plan (consecutive itinerary_day components, one tour). */
export function ItineraryDays({ days }: { days: Day[] }) {
  const src = days[0].source;
  return (
    <details className="group w-full max-w-md rounded-card border border-line bg-surface">
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 px-4 py-2.5 text-brand-sm font-semibold">
        <span>
          Day by day: {src.title} ({days.length} days)
        </span>
        <span aria-hidden className="text-muted transition-transform group-open:rotate-180">
          ▾
        </span>
      </summary>
      <ol className="flex flex-col gap-3 border-t border-line px-4 py-3">
        {days.map((d) => (
          <li key={d.day} className="flex gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-brand-xs font-bold text-brand-white">
              {d.day}
            </span>
            <div className="min-w-0">
              <h4 className="text-brand-sm font-semibold">{d.title.replace(/^Day \d+:\s*/, "")}</h4>
              <p className="mt-0.5 text-brand-sm">{d.description}</p>
              {(d.meals || d.stay) && (
                <p className="mt-1 text-brand-xs text-muted">
                  {d.meals ? `Meals: ${d.meals}` : ""}
                  {d.meals && d.stay ? " · " : ""}
                  {d.stay ? `Stay: ${d.stay}` : ""}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
      <p className="px-4 pb-3 text-brand-xs text-muted">Source: {src.doc_id}</p>
    </details>
  );
}
