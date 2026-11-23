"use client";

import type { ComponentOf } from "@/lib/catalog-schema";

import type { Actions } from "./registry";
import { Card, Pill } from "./ui";

type Props = ComponentOf<"tour_card"> & { actions: Actions; showAction?: boolean };

/** A published tour: facts and a reason only. Never a price (that comes from a quote). */
export function TourCard({ tour_id, title, duration, start, highlights, why, accent, bookable, source, actions, showAction = true }: Props) {
  return (
    <Card accent={accent} label={title}>
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
            <li key={h}>{h}</li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
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
