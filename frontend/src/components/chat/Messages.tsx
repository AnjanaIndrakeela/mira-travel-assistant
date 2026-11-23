import type { Source, UIComponent } from "@/lib/api";
import { brand } from "@/lib/brand";

export type ChatItem =
  | { id: string; role: "traveller"; text: string }
  | { id: string; role: "mira"; text: string; sources?: Source[]; ui?: UIComponent[] };

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-card rounded-br-sm bg-ink px-4 py-2.5 text-brand-md text-brand-white sm:max-w-[75%]">
        {text}
      </p>
    </div>
  );
}

/** Source chips: which pages of our content the answer used ([1], [2], ...). */
export function SourceChips({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <ul aria-label="Sources" className="mt-2 flex flex-wrap gap-1.5">
      {sources.map((s) => (
        <li
          key={s.n}
          title={`${s.title} – ${s.section}`}
          className="max-w-full truncate rounded-button border border-line bg-surface px-2.5 py-1 text-brand-xs text-muted"
        >
          <span className="font-semibold text-ink">[{s.n}]</span> {s.title}
          {s.section && s.section !== "Overview" ? ` – ${s.section}` : ""}
        </li>
      ))}
    </ul>
  );
}

export function AssistantMessage({ text, sources = [] }: { text: string; sources?: Source[] }) {
  return (
    <div className="flex items-start gap-2.5">
      <span
        aria-hidden
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-orange text-brand-xs font-bold text-ink"
      >
        {brand.assistantName[0]}
      </span>
      <div className="min-w-0 max-w-[85%] sm:max-w-[75%]">
        <p className="sr-only">{brand.assistantName} says:</p>
        <p className="whitespace-pre-wrap break-words rounded-card rounded-tl-sm border border-line bg-surface px-4 py-2.5 text-brand-md">
          {text}
        </p>
        <SourceChips sources={sources} />
      </div>
    </div>
  );
}

export function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2.5" role="status" aria-live="polite">
      <span aria-hidden className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-orange text-brand-xs font-bold text-ink">
        {brand.assistantName[0]}
      </span>
      <span className="text-brand-sm text-muted">{brand.assistantName} is thinking…</span>
    </div>
  );
}

export function MessageList({ items, thinking }: { items: ChatItem[]; thinking: boolean }) {
  return (
    <ol className="flex flex-col gap-4" aria-label="Conversation">
      {items.map((m) => (
        <li key={m.id}>
          {m.role === "traveller" ? (
            <UserMessage text={m.text} />
          ) : (
            <AssistantMessage text={m.text} sources={m.sources} />
          )}
        </li>
      ))}
      {thinking && (
        <li>
          <ThinkingIndicator />
        </li>
      )}
    </ol>
  );
}
