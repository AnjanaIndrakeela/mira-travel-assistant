import Image from "next/image";

import { type Actions, UIBlocks } from "@/components/catalog/registry";
import { brand } from "@/lib/brand";

import { Markdown } from "./Markdown";
import { ReplySkeleton, Stages } from "./Progress";

/** Shared bubble shape for every message. */
const BUBBLE = "rounded-2xl";

export type ChatItem =
  | { id: string; role: "traveller"; text: string }
  | { id: string; role: "mira"; text: string; ui?: unknown[] }
  | { id: string; role: "specialist"; text: string };

/** A reply from a person on the team: shown exactly as written, and clearly not from Mira. */
export function SpecialistMessage({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        aria-hidden
        className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-b from-[#1FA197] to-[#0F6B64] text-brand-white shadow-[0_1px_0_rgba(255,255,255,0.35)_inset,0_6px_12px_-6px_rgba(20,131,123,0.7)]"
      >
        <svg viewBox="0 0 16 16" className="h-5 w-5" fill="currentColor">
          <circle cx="8" cy="5" r="3" />
          <path d="M2 14.5c0-3 2.7-5 6-5s6 2 6 5z" />
        </svg>
      </span>
      <div className="min-w-0 flex-1">
        <p className="mb-1 text-brand-xs font-semibold text-muted">
          Travel specialist · {brand.name}
        </p>
        <div className={`w-fit max-w-full whitespace-pre-wrap break-words ${BUBBLE} rounded-tl-sm border border-accent-teal/40 bg-gradient-to-br from-[#F1FAF9] via-white to-[#E4F4F2] px-4 py-3 shadow-[0_1px_0_#fff_inset,0_-2px_0_rgba(20,131,123,0.08)_inset,0_12px_28px_-16px_rgba(20,131,123,0.55),0_2px_4px_rgba(17,17,17,0.05)] text-brand-md sm:max-w-[85%] lg:max-w-[46rem]`}>
          {text}
        </div>
      </div>
    </div>
  );
}

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className={`${BUBBLE} max-w-[85%] whitespace-pre-wrap break-words rounded-br-sm bg-gradient-to-br from-[#3A3A3A] via-[#1E1E1E] to-[#0B0B0B] px-4 py-3 text-brand-md text-brand-white shadow-[0_1px_0_rgba(255,255,255,0.18)_inset,0_-2px_0_rgba(0,0,0,0.35)_inset,0_12px_26px_-14px_rgba(17,17,17,0.7),0_3px_0_-1px_rgba(242,107,29,0.85)] sm:max-w-[75%]`}>
        {text}
      </p>
    </div>
  );
}

/** Mira's logo beside each of her messages. */
function Avatar() {
  return (
    <span
      aria-hidden
      className="mt-0.5 flex h-9 w-9 shrink-0 rounded-full shadow-[0_6px_12px_-6px_rgba(242,107,29,0.55)]"
    >
      <Image src="/mira-avatar.png" alt="" width={36} height={36} priority className="h-9 w-9 rounded-full" />
    </span>
  );
}

/** Mira's text, then the catalog components code chose for this turn (validated again here). */
export function AssistantMessage({ text, ui = [], actions }: { text: string; ui?: unknown[]; actions?: Actions }) {
  return (
    <div className="flex items-start gap-2.5">
      <Avatar />
      <div className="min-w-0 flex-1">
        <p className="sr-only">{brand.assistantName} says:</p>
        <div className={`w-fit max-w-full break-words ${BUBBLE} rounded-tl-sm border border-white bg-gradient-to-br from-white via-white to-[#FFF4EC] px-4 py-3 shadow-[0_1px_0_#fff_inset,0_-2px_0_rgba(17,17,17,0.04)_inset,0_14px_30px_-18px_rgba(17,17,17,0.45),0_2px_5px_rgba(17,17,17,0.06),0_0_0_1px_rgba(17,17,17,0.04)] text-brand-md sm:max-w-[85%] lg:max-w-[46rem]`}>
          <Markdown text={text} />
        </div>
        {actions && ui.length > 0 && <UIBlocks components={ui} actions={actions} />}
      </div>
    </div>
  );
}

/** Live progress: the current step in words, the four stages (on narrow screens; wide ones show
 * them in the trip panel) and a placeholder where the reply will appear. */
export function ThinkingIndicator({ step, stage }: { step: string | null; stage: number }) {
  return (
    <div className="reveal flex items-start gap-2.5">
      <Avatar />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="text-brand-sm text-muted" role="status" aria-live="polite">
          {step ? `${step}…` : `${brand.assistantName} is thinking…`}
        </span>
        <div className="lg:hidden">
          <Stages current={stage} compact />
        </div>
        <ReplySkeleton />
      </div>
    </div>
  );
}

export function MessageList({ items, thinking, step, stage, send }: {
  items: ChatItem[];
  thinking: boolean;
  step: string | null;
  stage: number;
  send: (text: string) => void;
}) {
  const lastMira = [...items].reverse().find((m) => m.role === "mira")?.id;
  return (
    <ol className="flex flex-col gap-4" aria-label="Conversation">
      {items.map((m) => (
        <li key={m.id} className="reveal">
          {m.role === "traveller" ? (
            <UserMessage text={m.text} />
          ) : m.role === "specialist" ? (
            <SpecialistMessage text={m.text} />
          ) : (
            <AssistantMessage text={m.text} ui={m.ui} actions={{ send, busy: thinking, latest: m.id === lastMira }} />
          )}
        </li>
      ))}
      {thinking && (
        <li>
          <ThinkingIndicator step={step} stage={stage} />
        </li>
      )}
    </ol>
  );
}
