"use client";

// One Mira reply rendered from its A2UI v1.0 messages (createSurface, updateComponents) with
// @a2ui/react. Each reply has its own processor and surface. If the messages can't be processed,
// the reply falls back to the plain component list, so a card is never lost.

import { A2uiSurface } from "@a2ui/react";
import { MessageProcessor, STRICT_VALIDATION } from "@a2ui/web_core";
import { Component, type ReactNode, useMemo } from "react";

import { type Actions, type CardAction, UIBlocks } from "@/components/catalog/registry";
import { ActionsContext, miraCatalog } from "@/lib/a2ui/catalog";

import { actionMessage } from "./Messages";

type Model = { type: string; properties: Record<string, unknown> };

class Fallback extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    console.warn("An A2UI surface failed to render; showing the plain components.");
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export default function A2uiReply({ messages, ui, actions }: {
  messages: unknown[];
  ui: unknown[];
  actions: Actions;
}) {
  const surfaces = useMemo(() => {
    try {
      // strict: a component our catalog doesn't have is refused here, not just left unrendered
      const processor = new MessageProcessor([miraCatalog], undefined, { validationConfig: STRICT_VALIDATION });
      processor.processMessages(messages as Parameters<typeof processor.processMessages>[0]);
      return [...processor.getSurfaces().entries()];
    } catch (err) {
      console.warn("A2UI messages were rejected; showing the plain components.", err);
      return null;
    }
  }, [messages]);
  // A click becomes an A2UI action from this surface: sourceComponentId is the clicked card's id
  // (the one of that component whose props match the action's context, e.g. its tour_id).
  const surfaceActions = useMemo<Actions>(() => {
    if (!surfaces?.length) return actions;
    const [surfaceId, surface] = surfaces[0];
    const act = (a: CardAction, label: string) => {
      const all = [...surface.componentsModel.getAll().entries()].map(
        ([id, m]) => [id, { type: m.type, properties: m.properties as Record<string, unknown> }] as [string, Model],
      );
      const same = all.filter(([, m]) => m.type === a.component);
      const match = same.find(([, m]) => Object.entries(a.context).every(([k, v]) => !(k in m.properties) || m.properties[k] === v));
      actions.sendAction(actionMessage(a, surfaceId, (match ?? same[0])?.[0] ?? "root"), label);
    };
    return { ...actions, act };
  }, [surfaces, actions]);
  const plain = <UIBlocks components={ui} actions={actions} />;
  if (!surfaces?.length) return plain;
  return (
    <ActionsContext.Provider value={surfaceActions}>
      <Fallback fallback={plain}>
        {surfaces.map(([id, surface]) => (
          <div key={id} data-a2ui-surface={id}>
            <A2uiSurface surface={surface} />
          </div>
        ))}
      </Fallback>
    </ActionsContext.Provider>
  );
}
