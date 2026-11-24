import { type Actions, UIBlocks } from "@/components/catalog/registry";
import { brand } from "@/lib/brand";

import { Markdown } from "./Markdown";
import { ReplySkeleton, Stages } from "./Progress";

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
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-teal text-brand-white"
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4" fill="currentColor">
          <circle cx="8" cy="5" r="3" />
          <path d="M2 14.5c0-3 2.7-5 6-5s6 2 6 5z" />
        </svg>
      </span>
      <div className="min-w-0 flex-1">
        <p className="mb-1 text-brand-xs font-semibold text-muted">
          Travel specialist · {brand.name}
        </p>
        <div className="w-fit max-w-full whitespace-pre-wrap break-words rounded-card rounded-tl-sm border-2 border-accent-teal bg-surface px-4 py-2.5 text-brand-md sm:max-w-[85%] lg:max-w-[46rem]">
          {text}
        </div>
      </div>
    </div>
  );
}

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-card rounded-br-sm bg-ink px-4 py-2.5 text-brand-md text-brand-white sm:max-w-[75%]">
        {text}
      </p>
    </div>
  );
}

function Avatar() {
  return (
    <span
      aria-hidden
      className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-orange text-brand-xs font-bold text-ink"
    >
      {brand.assistantName[0]}
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
        <div className="w-fit max-w-full break-words rounded-card rounded-tl-sm border border-line bg-surface px-4 py-2.5 text-brand-md sm:max-w-[85%] lg:max-w-[46rem]">
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
