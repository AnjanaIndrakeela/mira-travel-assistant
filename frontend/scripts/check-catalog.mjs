// Drift check (11.5): the Zod catalog must match the JSON Schema the backend exports.
// For every component type it compares the property names, the required ones and the enum
// values. Run: npm run check:catalog   (after `python -m app.ui.export` in the backend)
// It also proves the browser rejects bad payloads.

import { readFileSync } from "node:fs";
import { z } from "zod";

import { catalog, parseComponent } from "../src/lib/catalog-schema.ts";

const exported = JSON.parse(readFileSync(new URL("../src/lib/catalog.schema.json", import.meta.url), "utf8"));
const backend = {};
for (const def of Object.values(exported.$defs)) {
  const type = def.properties?.type?.const;
  if (type) backend[type] = def;
}

const problems = [];
const sorted = (xs) => [...xs].sort().join(", ");
const enums = (prop) => {
  const p = prop?.anyOf ? prop.anyOf.find((x) => x.type !== "null") : prop;
  return sorted(p?.enum ?? p?.items?.enum ?? []);
};

if (sorted(Object.keys(backend)) !== sorted(Object.keys(catalog)))
  problems.push(`types differ: backend [${sorted(Object.keys(backend))}] vs zod [${sorted(Object.keys(catalog))}]`);

for (const [type, schema] of Object.entries(catalog)) {
  const b = backend[type];
  if (!b) continue;
  const f = z.toJSONSchema(schema, { io: "input", unrepresentable: "any" });
  if (sorted(Object.keys(b.properties)) !== sorted(Object.keys(f.properties)))
    problems.push(`${type}: props backend [${sorted(Object.keys(b.properties))}] vs zod [${sorted(Object.keys(f.properties))}]`);
  if (sorted(b.required ?? []) !== sorted(f.required ?? []))
    problems.push(`${type}: required backend [${sorted(b.required ?? [])}] vs zod [${sorted(f.required ?? [])}]`);
  for (const key of Object.keys(b.properties)) {
    if (f.properties[key] && enums(b.properties[key]) !== enums(f.properties[key]))
      problems.push(`${type}.${key}: enum backend [${enums(b.properties[key])}] vs zod [${enums(f.properties[key])}]`);
  }
}

// The browser's own gate: these must all be rejected.
console.warn = () => {};
const id = "3f2a6c1e-0b4d-4e8a-9c7f-1a2b3c4d5e6f";
const card = { type: "tour_card", tour_id: "T01", title: "Tour", duration: "1 day", accent: "teal", bookable: true,
  source: { doc_id: "T01", title: "Tour" } };
const bad = [
  { type: "script", src: "x" },
  { ...card, title: "<script>alert(1)</script>" },
  { ...card, why: "Only USD 9" },
  { ...card, extra: 1 },
  { type: "price_breakdown", quote_id: id, price_usd: 1 },
];
bad.forEach((p, i) => parseComponent(p) && problems.push(`bad payload ${i} was accepted`));
if (!parseComponent(card)) problems.push("a valid tour_card was rejected");

if (problems.length) {
  console.error("Catalog check failed:\n- " + problems.join("\n- "));
  process.exit(1);
}
console.log(`Catalog check passed: ${Object.keys(catalog).length} components match the backend; bad payloads rejected.`);
