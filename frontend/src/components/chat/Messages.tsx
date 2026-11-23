import { type Actions, UIBlocks } from "@/components/catalog/registry";
import { brand } from "@/lib/brand";

export type ChatItem =
  | { id: string; role: "traveller"; text: string }
  | { id: string; role: "mira"; text: string; ui?: unknown[] };

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
        <p className="w-fit max-w-full whitespace-pre-wrap break-words rounded-card rounded-tl-sm border border-line bg-surface px-4 py-2.5 text-brand-md sm:max-w-[85%]">
          {text}
        </p>
        {actions && ui.length > 0 && <UIBlocks components={ui} actions={actions} />}
      </div>
    </div>
  );
}

export function ThinkingIndicator({ step }: { step: string | null }) {
  return (
    <div className="flex items-center gap-2.5" role="status" aria-live="polite">
      <Avatar />
      <span className="text-brand-sm text-muted">
        {step ? `${step}…` : `${brand.assistantName} is thinking…`}
      </span>
    </div>
  );
}

export function MessageList({ items, thinking, step, send }: {
  items: ChatItem[];
  thinking: boolean;
  step: string | null;
  send: (text: string) => void;
}) {
  const lastMira = [...items].reverse().find((m) => m.role === "mira")?.id;
  return (
    <ol className="flex flex-col gap-4" aria-label="Conversation">
      {items.map((m) => (
        <li key={m.id}>
          {m.role === "traveller" ? (
            <UserMessage text={m.text} />
          ) : (
            <AssistantMessage text={m.text} ui={m.ui} actions={{ send, busy: thinking, latest: m.id === lastMira }} />
          )}
        </li>
      ))}
      {thinking && (
        <li>
          <ThinkingIndicator step={step} />
        </li>
      )}
    </ol>
  );
}
