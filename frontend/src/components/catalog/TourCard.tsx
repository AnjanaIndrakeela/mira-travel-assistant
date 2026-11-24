"use client";

import { mediaUrl } from "@/lib/api";
import type { ComponentOf } from "@/lib/catalog-schema";

import { Inline } from "../chat/Markdown";
import { Credits } from "./Photo";
import type { Actions } from "./registry";
import { Card, Pill } from "./ui";

type Props = ComponentOf<"tour_card"> & { actions: Actions; showAction?: boolean };

/** A published tour: facts and a reason only. Never a price (that comes from a quote). */
export function TourCard({ tour_id, title, duration, start, highlights, why, accent, bookable, source, images, actions, showAction = true }: Props) {
  const [main, ...more] = images;
  return (
    <Card accent={accent} label={title} fluid>
      {main && (
        <div className="-mx-4 -mt-4 mb-1 flex flex-col gap-1">
          {/* eslint-disable-next-line @next/next/no-img-element -- files from our own media route, already sized and cached */}
          <img
            src={mediaUrl(main.src)}
            alt={main.alt}
            loading="lazy"
            decoding="async"
            className="aspect-[16/9] w-full bg-line object-cover"
          />
          {more.length > 0 && (
            <div className="grid grid-cols-2 gap-1 px-1">
              {more.map((img) => (
                // eslint-disable-next-line @next/next/no-img-element -- as above
                <img
                  key={img.src}
                  src={mediaUrl(img.src)}
                  alt={img.alt}
                  loading="lazy"
                  decoding="async"
                  className="aspect-[16/9] w-full rounded-sm bg-line object-cover"
                />
              ))}
            </div>
          )}
          <div className="px-4">
            <Credits images={images} />
          </div>
        </div>
      )}
      <div>
        <h3 className="text-brand-md font-semibold leading-snug">{title}</h3>
        <p className="mt-0.5 text-brand-sm text-muted">
          {duration}
          {start ? ` · from ${start.startsWith("Your ") ? `y${start.slice(1)}` : start}` : ""}
        </p>
      </div>
      {why && <p className="text-brand-sm">{why}</p>}
      {highlights.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-4 text-brand-sm">
          {highlights.map((h) => (
            <li key={h}><Inline text={h} /></li>
          ))}
        </ul>
      )}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1">
        <span className="text-brand-xs text-muted" title={source.title}>
          Source: {source.doc_id}
        </span>
        {showAction && (
          <Pill
            variant={bookable ? "primary" : "outline"}
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
