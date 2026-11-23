// The UI catalog again, in Zod: the browser checks every component before rendering it (11.5).
// It mirrors backend/app/ui/catalog.py. `npm run check:catalog` compares it with the JSON
// Schema the backend exports (catalog.schema.json), so the two can't drift apart unnoticed.
// Anything that fails here is not rendered at all.

import { z } from "zod";

// Same rules as the backend: no markup or script, and no money amounts in text props
// (prices only ever come from /quotes/{id}).
const UNSAFE = /<\s*\/?\s*[a-z!]|javascript\s*:|data\s*:\s*text\/html|\bon[a-z]+\s*=/i;
const MONEY = /(?:\$|US\$|USD|LKR|Rs\.?|€|£)\s?\d|\d[\d,.]*\s?(?:USD|LKR|dollars?)\b/i;

const text = (max: number) =>
  z
    .string()
    .min(1)
    .max(max)
    .refine((s) => !UNSAFE.test(s), "markup or script")
    .refine((s) => !MONEY.test(s), "money amount");

const tourId = z.string().regex(/^T\d{2}$/);
const docId = z.string().regex(/^[A-Z]{1,3}\d{2,3}$/);
export const accents = ["teal", "leaf", "sun", "sky", "coral"] as const;

const sourceRef = z.strictObject({ doc_id: docId, title: text(120) });

export const TravellerPicker = z.strictObject({
  type: z.literal("traveller_picker"),
  adults: z.number().int().min(1).max(20).default(2),
  child_ages: z.array(z.number().int().min(0).max(17)).max(10).default([]),
  ask_child_ages: z.boolean().default(false),
});

export const TourCard = z.strictObject({
  type: z.literal("tour_card"),
  tour_id: tourId,
  title: text(120),
  duration: text(40),
  start: text(120).nullable().default(null),
  highlights: z.array(text(160)).max(4).default([]),
  why: text(200).nullable().default(null),
  accent: z.enum(accents),
  bookable: z.boolean(),
  source: sourceRef,
});

export const ItineraryDay = z.strictObject({
  type: z.literal("itinerary_day"),
  tour_id: tourId,
  day: z.number().int().min(1).max(30),
  title: text(160),
  description: text(1200),
  meals: text(80).nullable().default(null),
  stay: text(160).nullable().default(null),
  source: sourceRef,
});

/** Quote ID only: the component fetches the verified public quote itself. */
export const PriceBreakdown = z.strictObject({
  type: z.literal("price_breakdown"),
  quote_id: z.uuid(),
});

export const BookingForm = z.strictObject({
  type: z.literal("booking_form"),
  quote_id: z.uuid(),
  fields: z
    .array(z.enum(["name", "email", "phone", "card_number"]))
    .min(1)
    .default(["name", "email", "card_number"]),
});

export const SpecialistNotice = z.strictObject({
  type: z.literal("specialist_notice"),
  reason: z.enum(["no_price", "custom_request", "unanswered_question", "handoff", "booking_failed"]),
  message: text(400),
  enquiry_id: z.uuid().nullable().default(null),
});

export const SourceList = z.strictObject({
  type: z.literal("source_list"),
  items: z
    .array(
      z.strictObject({
        n: z.number().int().min(1).max(20),
        doc_id: docId,
        title: text(120),
        section: text(160),
      }),
    )
    .min(1)
    .max(8),
});

export const WelcomeBack = z.strictObject({
  type: z.literal("welcome_back"),
  tour_title: text(120),
  quote_id: z.uuid().nullable().default(null),
});

export const UIComponentSchema = z.discriminatedUnion("type", [
  TravellerPicker,
  TourCard,
  ItineraryDay,
  PriceBreakdown,
  BookingForm,
  SpecialistNotice,
  SourceList,
  WelcomeBack,
]);

export type UIComponent = z.infer<typeof UIComponentSchema>;
export type ComponentOf<T extends UIComponent["type"]> = Extract<UIComponent, { type: T }>;

/** The catalog's components by type, for the drift check. */
export const catalog = {
  traveller_picker: TravellerPicker,
  tour_card: TourCard,
  itinerary_day: ItineraryDay,
  price_breakdown: PriceBreakdown,
  booking_form: BookingForm,
  specialist_notice: SpecialistNotice,
  source_list: SourceList,
  welcome_back: WelcomeBack,
} as const;

/** Parse one payload from the server; null (and a console warning) if it isn't in the catalog. */
export function parseComponent(raw: unknown): UIComponent | null {
  const res = UIComponentSchema.safeParse(raw);
  if (res.success) return res.data;
  const type = raw && typeof raw === "object" && "type" in raw ? String(raw.type) : "unknown";
  console.warn(`UI component rejected in the browser: ${type}`);
  return null;
}
