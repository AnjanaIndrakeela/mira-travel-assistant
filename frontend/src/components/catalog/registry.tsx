"use client";

// The component registry (11.6): only catalog types render, and only after Zod accepts the
// payload. Anything else renders nothing. Each component has its own error boundary, so one
// broken card can never take the chat down.

import { Component, type ReactNode } from "react";

import type { ActionMessage } from "@/lib/api";
import { type ComponentOf, parseComponent, type UIComponent } from "@/lib/catalog-schema";

import { BookingForm } from "./BookingForm";
import { ItineraryDays } from "./ItineraryDays";
import { PhotoGallery } from "./Photo";
import { PriceBreakdown } from "./PriceBreakdown";
import { SourceList } from "./SourceList";
import { SpecialistNotice } from "./SpecialistNotice";
import { TourCard } from "./TourCard";
import { TravellerPicker } from "./TravellerPicker";
import { TripPlan } from "./TripPlan";
import { WelcomeBack } from "./WelcomeBack";

/** A click on a card: an A2UI action name and its typed context (see backend app/ui/actions.py). */
export type CardAction = {
  name: "get_price" | "ask_team" | "set_travellers" | "new_quote" | "packing_tips" | "plan_another";
  context: Record<string, unknown>;
  /** The catalog component the click came from (TourCard...), for the action's sourceComponentId. */
  component: string;
};

export type Actions = {
  /** Send a message to Mira as the traveller. */
  send: (text: string) => void;
  /** Send a click as an A2UI action; `label` is what the traveller's bubble shows. */
  act: (action: CardAction, label: string) => void;
  /** Send a full A2UI action message (A2uiReply uses it to name the surface and component). */
  sendAction: (action: ActionMessage, label: string) => void;
  /** True while Mira is replying (buttons that send are disabled). */
  busy: boolean;
  /** Only the newest reply's pickers and buttons are live. */
  latest: boolean;
};

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    console.warn("A UI component failed to render and was hidden.");
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

type Block =
  | { kind: "one"; c: UIComponent }
  | { kind: "tours"; cards: ComponentOf<"tour_card">[] }
  | { kind: "days"; days: ComponentOf<"itinerary_day">[] };

/** Group neighbours: tour cards side by side, itinerary days in one collapsible list. */
function group(components: UIComponent[]): Block[] {
  const out: Block[] = [];
  for (const c of components) {
    const last = out[out.length - 1];
    if (c.type === "tour_card") {
      if (last?.kind === "tours") last.cards.push(c);
      else out.push({ kind: "tours", cards: [c] });
    } else if (c.type === "itinerary_day") {
      if (last?.kind === "days" && last.days[0].tour_id === c.tour_id) last.days.push(c);
      else out.push({ kind: "days", days: [c] });
    } else out.push({ kind: "one", c });
  }
  return out;
}

function renderOne(c: UIComponent, actions: Actions): ReactNode {
  switch (c.type) {
    case "traveller_picker":
      return <TravellerPicker {...c} actions={actions} />;
    case "price_breakdown":
      return <PriceBreakdown {...c} />;
    case "booking_form":
      return <BookingForm {...c} actions={actions} />;
    case "specialist_notice":
      return <SpecialistNotice {...c} />;
    case "source_list":
      return <SourceList {...c} />;
    case "welcome_back":
      return <WelcomeBack {...c} />;
    case "photo_gallery":
      return <PhotoGallery {...c} />;
    case "trip_plan":
      return <TripPlan {...c} />;
    default:
      return null; // tour_card and itinerary_day are grouped; nothing else exists
  }
}

export function UIBlocks({ components, actions }: { components: unknown[]; actions: Actions }) {
  const parsed = components.map(parseComponent).filter((c): c is UIComponent => c !== null);
  if (!parsed.length) return null;
  const priced = parsed.some((c) => c.type === "price_breakdown"); // the card's tour is already priced
  return (
    <div className="mt-3 flex flex-col gap-3">
      {group(parsed).map((b, i) => (
        <Boundary key={i}>
          {b.kind === "tours" ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3" aria-label="Tours">
              {b.cards.map((c) => (
                <TourCard key={c.tour_id} {...c} actions={actions} showAction={!priced} />
              ))}
            </div>
          ) : b.kind === "days" ? (
            <ItineraryDays days={b.days} />
          ) : (
            renderOne(b.c, actions)
          )}
        </Boundary>
      ))}
    </div>
  );
}
