// A2UI <-> Mira card shapes, kept free of React so `npm run check:a2ui` can import it.

/** TourCard -> tour_card (the reverse of the backend's a2ui_name). */
export function typeOf(name: string): string {
  return name.replace(/(?<!^)([A-Z])/g, "_$1").toLowerCase();
}

/** {id, component: "TourCard", ...props} -> {type: "tour_card", ...props}; "@" keys dropped. */
export function fromA2ui(name: string, properties: Record<string, unknown>): Record<string, unknown> {
  const props = Object.fromEntries(
    Object.entries(properties).filter(([k]) => k !== "id" && k !== "component" && !k.startsWith("@")),
  );
  return { type: typeOf(name), ...props };
}
