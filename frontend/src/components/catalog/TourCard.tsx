"use client";

import { mediaUrl } from "@/lib/api";
import type { ComponentOf } from "@/lib/catalog-schema";

import { Inline } from "../chat/Markdown";
import { Credits } from "./Photo";
import type { Actions } from "./registry";
import { ACCENT_TEXT, Card, Chip, Icon, Pill } from "./ui";

type Props = ComponentOf<"tour_card"> & { actions: Actions; showAction?: boolean };

/** A published tour: facts and a reason only. Never a price (that comes from a quote). */
export function TourCard({ tour_id, title, duration, start, highlights, why, accent, bookable, source, images, actions, showAction = true }: Props) {
  const [main, ...more] = images;
  const from = start ? (start.startsWith("Your ") ? `y${start.slice(1)}` : start) : null;
  const chips = (
    <>
      <Chip icon="clock" tone={main ? "glass" : "plain"}>{duration}</Chip>
      <Chip icon={bookable ? "check" : "chat"} tone={main ? "glass" : "plain"}>
        {bookable ? "Book online" : "Tailor-made"}
      </Chip>
    </>
  );
  return (
    <Card label={title} fluid>
      {main ? (
        <div className="-mx-4 -mt-4 flex flex-col gap-1.5">
          <div className="group/photo relative overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element -- files from our own media route, already sized and cached */}
            <img
              src={mediaUrl(main.src)}
              alt={main.alt}
              loading="lazy"
              decoding="async"
              className="aspect-[16/9] w-full bg-line object-cover transition-transform group-hover/photo:scale-[1.03]"
            />
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-t from-brand-black/75 via-brand-black/10 to-transparent" />
            <div className="absolute left-3 right-3 top-3 flex flex-wrap gap-1.5">{chips}</div>
            <h3 className="absolute inset-x-4 bottom-3 text-brand-lg font-bold leading-tight text-brand-white [text-shadow:0_1px_8px_rgba(0,0,0,0.45)]">
              {title}
            </h3>
          </div>
          {more.length > 0 && (
            <div className="grid grid-cols-2 gap-1.5 px-1.5">
              {more.map((img) => (
                // eslint-disable-next-line @next/next/no-img-element -- as above
                <img
                  key={img.src}
                  src={mediaUrl(img.src)}
                  alt={img.alt}
                  loading="lazy"
                  decoding="async"
                  className="aspect-[16/9] w-full rounded-md bg-line object-cover"
                />
              ))}
            </div>
          )}
          <div className="px-4">
            <Credits images={images} />
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className={`h-1 w-10 rounded-full ${accent ? `bg-current ${ACCENT_TEXT[accent]}` : "bg-brand-orange"}`} />
          <h3 className="text-brand-lg font-bold leading-tight">{title}</h3>
          <div className="flex flex-wrap gap-1.5">{chips}</div>
        </div>
      )}

      {from && (
        <p className="flex items-center gap-1.5 text-brand-sm text-muted">
          <Icon name="calendar" className="h-4 w-4" />
          <span>From {from}</span>
        </p>
      )}

      {why && (
        <p className="flex gap-2 rounded-lg bg-brand-orange/[0.07] px-3 py-2 text-brand-sm">
          <Icon name="sparkle" className="mt-0.5 h-4 w-4 text-brand-orange" />
          <span>{why}</span>
        </p>
      )}

      {highlights.length > 0 && (
        <ul className="flex flex-col gap-1.5 text-brand-sm">
          {highlights.map((h) => (
            <li key={h} className="flex gap-2">
              <Icon name="check" className={`mt-0.5 h-4 w-4 ${accent ? ACCENT_TEXT[accent] : "text-accent-teal"}`} />
              <span className="min-w-0"><Inline text={h} /></span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line/70 pt-3">
        <span className="inline-flex items-center gap-1 text-brand-xs text-muted" title={source.title}>
          <Icon name="book" className="h-3.5 w-3.5" />
          {source.doc_id}
        </span>
        {showAction && (
          <Pill
            variant={bookable ? "primary" : "outline"}
            icon="arrow"
            disabled={actions.busy}
            onClick={() =>
              actions.send(bookable ? `I'd like a price for the ${title} (${tour_id}).` : `Can your team help me with the ${title}?`)
            }
          >
            {bookable ? "Get a price" : "Ask our team"}
          </Pill>
        )}
      </div>
    </Card>
  );
}
