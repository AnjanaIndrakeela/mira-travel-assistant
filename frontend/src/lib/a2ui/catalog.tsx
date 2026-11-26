"use client";

// Mira's A2UI v1.0 catalog for @a2ui/react (step 6 of the A2UI move).
//
// The backend sends each reply as one surface: a MiraReply root whose children are our catalog
// components (TourCard, PriceBreakdown...). The A2UI processor builds the surface; MiraReply then
// reads its children, turns each back into our {type, ...props} shape and renders them with the
// existing UIBlocks, which validates every one with Zod again and keeps the layout (tour cards
// side by side, a tour's days in one list). Unknown components render nothing.

import { createBinderlessComponentImplementation } from "@a2ui/react";
import { Catalog } from "@a2ui/web_core";
import { createContext, useContext } from "react";
import { z } from "zod"; // zod 3: the schema type @a2ui/web_core expects

import { type Actions, UIBlocks } from "@/components/catalog/registry";
import a2uiCatalog from "@/lib/a2ui-catalog.json";

import { fromA2ui } from "./convert";

export const CATALOG_ID: string = a2uiCatalog.catalogId;
export const ROOT = "MiraReply";

/** The chat's send/busy/latest, for the components inside a surface. */
export const ActionsContext = createContext<Actions | null>(null);

type Model = { type: string; properties: Record<string, unknown> };
type Ctx = {
  componentModel: Model;
  surfaceComponents: { get(id: string): Model | undefined };
};

function Blocks({ components }: { components: unknown[] }) {
  const actions = useContext(ActionsContext);
  return actions ? <UIBlocks components={components} actions={actions} /> : null;
}

// Props are checked by Zod in UIBlocks (the same rules as the backend's Pydantic catalog), so
// the processor's own schema only lets them through.
const anyProps = z.object({}).passthrough();

const reply = createBinderlessComponentImplementation(
  {
    name: ROOT,
    schema: z.object({ children: z.array(z.string()) }).passthrough(),
    allowedChildren: Object.keys(a2uiCatalog.components).filter((n) => n !== ROOT),
  },
  ({ context }) => {
    const ctx = context as unknown as Ctx;
    const ids = (ctx.componentModel.properties.children as string[] | undefined) ?? [];
    const children = ids
      .map((id) => ctx.surfaceComponents.get(id))
      .filter((m): m is Model => !!m && m.type !== ROOT)
      .map((m) => fromA2ui(m.type, m.properties));
    return <Blocks components={children} />;
  },
);

// Each of our ten components on its own (used only if one is ever a surface root).
const parts = Object.keys(a2uiCatalog.components)
  .filter((name) => name !== ROOT)
  .map((name) =>
    createBinderlessComponentImplementation({ name, schema: anyProps }, ({ context }) => (
      <Blocks components={[fromA2ui(name, (context as unknown as Ctx).componentModel.properties)]} />
    )),
  );

export const miraCatalog = new Catalog(CATALOG_ID, a2uiCatalog.a2uiVersion, [reply, ...parts]);
