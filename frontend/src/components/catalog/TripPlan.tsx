import type { ComponentOf } from "@/lib/catalog-schema";

import { Inline } from "../chat/Markdown";
import { Photo } from "./Photo";
import { Chip, Icon, IconBadge, SHADOW } from "./ui";

type Props = ComponentOf<"trip_plan">;

/** A plan Mira wrote for this traveller from our published pages: a draft, never priced here. */
export function TripPlan({ title, overview, days, sources, images }: Props) {
  return (
    <section
      aria-label="Your trip plan"
      className={`w-full max-w-md overflow-hidden rounded-card border border-line/80 bg-surface sm:max-w-none ${SHADOW}`}
    >
      {images[0] && <Photo image={images[0]} sizes="640px" className="aspect-[5/2]" />}
      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          <IconBadge name="sparkle" accent="sun" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Planned for you</p>
            <h3 className="text-brand-base font-semibold leading-snug">{title}</h3>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Chip icon="clock">{days.length} {days.length === 1 ? "day" : "days"}</Chip>
          <Chip icon="shield">Draft: our team confirms and prices it</Chip>
        </div>
        <p className="text-brand-sm leading-relaxed"><Inline text={overview} /></p>

        <ol className="relative mt-1 border-t border-line/70 pt-4">
          {days.map((d, i) => (
            <li key={d.day} className="relative flex gap-3.5 pb-5 last:pb-1">
              {i < days.length - 1 && (
                <span aria-hidden className="absolute bottom-0 left-[15px] top-8 w-0.5 rounded-full bg-gradient-to-b from-accent-sun/50 to-line" />
              )}
              <span className="relative z-[1] flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-brand-white ring-4 ring-surface">
                <span className="sr-only">Day </span>
                <span className="text-brand-xs font-bold">{d.day}</span>
              </span>
              <div className="min-w-0 flex-1 pt-1">
                <h4 className="text-brand-sm font-semibold leading-snug">{d.title.replace(/^Day \d+:\s*/, "")}</h4>
                <p className="mt-1 text-brand-sm leading-relaxed"><Inline text={d.description} /></p>
                {d.stay && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Chip icon="bed">{d.stay}</Chip>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
      {sources.length > 0 && (
        <p className="flex items-start gap-1 border-t border-line/70 bg-ink/[0.02] px-4 py-2 text-brand-xs text-muted">
          <Icon name="book" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Written from our pages: {sources.map((s) => s.title).join(" · ")}
        </p>
      )}
    </section>
  );
}
