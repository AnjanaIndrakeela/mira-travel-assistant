"use client";

// "Your trip": a summary beside the chat on wide screens (lg and up). Built only from the
// catalog components already shown (validated by Zod), so it never says anything the chat
// didn't. Prices stay in the price card: this panel only says whether the trip is priced.

import { Photo } from "@/components/catalog/Photo";
import { type ComponentOf, parseComponent, type UIComponent } from "@/lib/catalog-schema";

import type { ChatItem } from "./Messages";
import { Stages } from "./Progress";

type Trip = {
  tour: ComponentOf<"tour_card"> | null;
  priced: boolean;
  suggestions: ComponentOf<"tour_card">[];
  summary: string | null;
  gallery: ComponentOf<"photo_gallery"> | null;
};

export function tripFrom(items: ChatItem[]): Trip {
  const trip: Trip = { tour: null, priced: false, suggestions: [], summary: null, gallery: null };
  for (const m of items) {
    if (m.role !== "mira" || !m.ui?.length) continue;
    const ui = m.ui.map(parseComponent).filter((c): c is UIComponent => c !== null);
    const cards = ui.filter((c): c is ComponentOf<"tour_card"> => c.type === "tour_card");
    const priced = ui.some((c) => c.type === "price_breakdown");
    if (priced && cards[0]) {
      trip.tour = cards[0];
      trip.priced = true;
      trip.suggestions = [];
    } else if (cards.length > 1) {
      trip.suggestions = cards;
    } else if (cards.length === 1) {
      trip.tour = cards[0];
      trip.priced = false;
    }
    for (const c of ui) {
      if (c.type === "specialist_notice" && c.summary) trip.summary = c.summary;
      if (c.type === "photo_gallery") trip.gallery = c;
    }
  }
  return trip;
}

export function TripPanel({ items, thinking, stage }: { items: ChatItem[]; thinking: boolean; stage: number }) {
  const trip = tripFrom(items);
  const empty = !trip.tour && !trip.suggestions.length && !trip.summary && !trip.gallery;
  return (
    <aside aria-label="Your trip" className="flex max-h-[calc(100dvh-10rem)] flex-col gap-4 overflow-y-auto rounded-2xl border border-white bg-gradient-to-b from-white to-[#FAFAFA] p-4 shadow-[0_1px_0_#fff_inset,0_14px_30px_-18px_rgba(17,17,17,0.4),0_0_0_1px_rgba(17,17,17,0.05)]">
      <h2 className="text-brand-md font-semibold">Your trip</h2>

      {thinking && (
        <section className="reveal rounded-input bg-brand-orange/5 p-3">
          <h3 className="mb-2 text-brand-xs font-semibold uppercase tracking-wide text-muted">Working on it</h3>
          <Stages current={stage} />
        </section>
      )}

      {empty && !thinking && (
        <p className="text-brand-sm text-muted">
          Tell Mira where you&apos;d like to go, when, and who&apos;s travelling. The tour you pick and its status show up here.
        </p>
      )}

      {trip.tour && (
        <section className="reveal flex flex-col gap-2">
          {trip.tour.images[0] && <Photo image={trip.tour.images[0]} className="aspect-[16/9]" />}
          <div>
            <p className="text-brand-sm font-semibold leading-snug">{trip.tour.title}</p>
            <p className="text-brand-xs text-muted">{trip.tour.duration}</p>
          </div>
          <p
            className={`w-fit rounded-full px-2.5 py-0.5 text-brand-xs font-semibold ${
              trip.priced ? "bg-accent-leaf/15 text-ink" : "bg-line text-ink"
            }`}
          >
            {trip.priced ? "Priced: see the price card in the chat" : trip.tour.bookable ? "Not priced yet" : "Our team prices this one"}
          </p>
        </section>
      )}

      {trip.suggestions.length > 0 && (
        <section className="reveal flex flex-col gap-1.5">
          <h3 className="text-brand-xs font-semibold uppercase tracking-wide text-muted">Suggested tours</h3>
          <ul className="flex flex-col gap-1 text-brand-sm">
            {trip.suggestions.map((s) => (
              <li key={s.tour_id} className="flex justify-between gap-2">
                <span className="min-w-0 truncate">{s.title}</span>
                <span className="shrink-0 text-brand-xs text-muted">{s.duration.split("/")[0].trim()}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {trip.summary && (
        <section className="reveal">
          <h3 className="mb-1 text-brand-xs font-semibold uppercase tracking-wide text-muted">What you asked for</h3>
          <ul className="flex flex-col gap-0.5 text-brand-sm">
            {trip.summary.replace(/\.$/, "").split(". ").map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      {trip.gallery && !trip.tour && (
        <section className="reveal grid grid-cols-2 gap-1.5">
          {trip.gallery.images.slice(0, 4).map((img) => (
            <Photo key={img.src} image={img} className="aspect-square" />
          ))}
        </section>
      )}
    </aside>
  );
}
