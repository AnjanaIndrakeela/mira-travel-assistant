import type { ComponentOf } from "@/lib/catalog-schema";

import { Inline } from "../chat/Markdown";
import { Photo } from "./Photo";
import { Chip, Icon, IconBadge, SHADOW } from "./ui";

type Day = ComponentOf<"itinerary_day">;

/** A tour's published day-by-day plan (consecutive itinerary_day components, one tour), as a timeline. */
export function ItineraryDays({ days }: { days: Day[] }) {
  const src = days[0].source;
  return (
    <details className={`group w-full max-w-md overflow-hidden rounded-card border border-line/80 bg-surface sm:max-w-none ${SHADOW}`}>
      <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4 py-3 hover:bg-ink/[0.02] [&::-webkit-details-marker]:hidden">
        <IconBadge name="route" accent="teal" />
        <span className="min-w-0 flex-1">
          <span className="block text-brand-sm font-semibold leading-snug">Day by day: {src.title}</span>
          <span className="block text-brand-xs text-muted">
            {days.length} days · <span className="group-open:hidden">tap to see the plan</span>
            <span className="hidden group-open:inline">the published itinerary</span>
          </span>
        </span>
        <span aria-hidden className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink/[0.05] text-muted transition-transform group-open:rotate-180">
          <Icon name="chevron" />
        </span>
      </summary>

      <ol className="relative mx-4 mb-3 mt-1 border-t border-line/70 pt-4">
        {days.map((d, i) => (
          <li key={d.day} className="relative flex gap-3.5 pb-5 last:pb-1">
            {/* the timeline: a line from this day's dot to the next */}
            {i < days.length - 1 && (
              <span aria-hidden className="absolute bottom-0 left-[15px] top-8 w-0.5 rounded-full bg-gradient-to-b from-accent-teal/40 to-line" />
            )}
            <span className="relative z-[1] flex h-8 w-8 shrink-0 flex-col items-center justify-center rounded-full bg-ink text-brand-white ring-4 ring-surface">
              <span className="sr-only">Day </span>
              <span className="text-brand-xs font-bold">{d.day}</span>
            </span>
            <div className="min-w-0 flex-1 pt-1">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-accent-teal">Day {d.day}</p>
              <h4 className="text-brand-sm font-semibold leading-snug">{d.title.replace(/^Day \d+:\s*/, "")}</h4>
              {d.image && (
                <div className="mt-2 max-w-sm overflow-hidden">
                  <Photo image={d.image} sizes="384px" className="aspect-[2/1] rounded-lg" />
                </div>
              )}
              <p className="mt-1.5 text-brand-sm leading-relaxed"><Inline text={d.description} /></p>
              {(d.meals || d.stay) && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {d.meals && <Chip icon="meal">{d.meals}</Chip>}
                  {d.stay && <Chip icon="bed">{d.stay}</Chip>}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
      <p className="flex items-center gap-1 border-t border-line/70 bg-ink/[0.02] px-4 py-2 text-brand-xs text-muted">
        <Icon name="book" className="h-3.5 w-3.5" />
        Source: {src.doc_id}
      </p>
    </details>
  );
}
