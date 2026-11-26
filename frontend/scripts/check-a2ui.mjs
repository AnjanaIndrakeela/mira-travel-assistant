// A2UI check (step 9): the browser side of the A2UI move. Run: npm run check:a2ui
// - every component in the exported A2UI catalog maps to a Zod catalog type, and back;
// - a reply shaped like the backend's to_a2ui() output goes through the real @a2ui/web_core
//   MessageProcessor, and each child converts back to a card our Zod catalog accepts;
// - messages the renderer must refuse (unknown component, wrong catalog) are refused, so
//   A2uiReply falls back to the plain list.

import { readFileSync } from "node:fs";
import { Catalog, MessageProcessor, STRICT_VALIDATION } from "@a2ui/web_core";
import { z } from "zod"; // zod 3: what web_core expects

import { fromA2ui, typeOf } from "../src/lib/a2ui/convert.ts";
import { catalog, parseComponent } from "../src/lib/catalog-schema.ts";

const a2ui = JSON.parse(readFileSync(new URL("../src/lib/a2ui-catalog.json", import.meta.url), "utf8"));
const problems = [];
const sorted = (xs) => [...xs].sort().join(", ");
console.warn = () => {};

// 1. names: A2UI components <-> Zod types
const ROOT = "MiraReply";
const named = Object.keys(a2ui.components).filter((n) => n !== ROOT);
if (sorted(named.map(typeOf)) !== sorted(Object.keys(catalog)))
  problems.push(`A2UI [${sorted(named.map(typeOf))}] vs Zod [${sorted(Object.keys(catalog))}]`);
for (const n of named)
  if (a2ui.components[n]["x-mira-type"] !== typeOf(n)) problems.push(`${n} does not map to ${a2ui.components[n]["x-mira-type"]}`);
if (!a2ui.components[ROOT]) problems.push("the MiraReply root is missing from the catalog");

// 2. the real processor, with the same component names and permissive schemas as the app
const comp = (name, schema = z.object({}).passthrough()) => ({ name, schema });
const mira = new Catalog(a2ui.catalogId, a2ui.a2uiVersion,
  [comp(ROOT, z.object({ children: z.array(z.string()) }).passthrough()), ...named.map((n) => comp(n))]);
const id = "3f2a6c1e-0b4d-4e8a-9c7f-1a2b3c4d5e6f";
const tour = { tour_id: "T01", title: "Sigiriya day tour", duration: "1 day", accent: "teal", bookable: true,
  source: { doc_id: "T01", title: "Sigiriya day tour" } };
const reply = (components, catalogId = a2ui.catalogId, surfaceId = "reply-1-abc") => [
  { version: "1.0", createSurface: { surfaceId, catalogId } },
  { version: "1.0", updateComponents: { surfaceId, components } },
];
const good = reply([
  { id: "root", component: ROOT, children: ["c1", "c2", "c3"] },
  { id: "c1", component: "TourCard", ...tour },
  { id: "c2", component: "PriceBreakdown", quote_id: id },
  { id: "c3", component: "BookingForm", quote_id: id, fields: ["name", "email", "phone", "card"] },
]);
try {
  const p = new MessageProcessor([mira], undefined, { validationConfig: STRICT_VALIDATION });
  p.processMessages(good);
  const surface = p.getSurface("reply-1-abc");
  if (!surface) throw new Error("no surface");
  const all = surface.componentsModel.getAll();
  const children = all.get("root").properties.children;
  if (sorted(children) !== "c1, c2, c3") problems.push(`root children: ${children}`);
  for (const cid of children) {
    const m = all.get(cid);
    const card = fromA2ui(m.type, m.properties);
    if (!parseComponent(card)) problems.push(`${m.type} did not convert back to a valid card: ${JSON.stringify(card)}`);
  }
} catch (err) {
  problems.push(`a valid reply was refused: ${err.message}`);
}

// 3. what must be refused
const refused = {
  "an unknown component": reply([{ id: "root", component: ROOT, children: ["c1"] }, { id: "c1", component: "Script", src: "x" }]),
  "another catalog": reply([{ id: "root", component: ROOT, children: [] }], "https://evil.example/catalog"),
};
for (const [what, msgs] of Object.entries(refused)) {
  try {
    new MessageProcessor([mira], undefined, { validationConfig: STRICT_VALIDATION }).processMessages(msgs);
    problems.push(`${what} was accepted`);
  } catch {
    /* refused, as it should be */
  }
}

// 4. and the Zod gate still holds after conversion: a bad card from a surface renders nothing
if (parseComponent(fromA2ui("TourCard", { id: "c1", component: "TourCard", ...tour, title: "<b>x</b>" })))
  problems.push("a TourCard with markup in its title was accepted");

if (problems.length) {
  console.error("A2UI check failed:\n- " + problems.join("\n- "));
  process.exit(1);
}
console.log(`A2UI check passed: ${named.length} components + ${ROOT}; the processor builds a reply and refuses bad ones.`);
