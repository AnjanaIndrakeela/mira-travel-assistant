"use client";

import { useRef, useState } from "react";

const MAX = 2000;

type Props = { onSend: (text: string) => void; disabled: boolean };

/** Enter sends, Shift+Enter adds a line. Disabled while Mira is replying. */
export function Composer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const trimmed = text.trim();

  function send() {
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    ref.current?.focus();
  }

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <label htmlFor="message" className="sr-only">
        Message
      </label>
      <textarea
        id="message"
        ref={ref}
        rows={1}
        value={text}
        maxLength={MAX}
        placeholder="Ask Mira about a trip…"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send();
          }
        }}
        className="max-h-40 min-h-11 flex-1 resize-none rounded-input border border-line bg-surface px-3.5 py-2.5 text-brand-md outline-none transition-colors placeholder:text-muted focus:border-ink"
      />
      <button
        type="submit"
        disabled={disabled || !trimmed}
        className="h-11 shrink-0 rounded-button bg-brand-orange px-5 text-brand-md font-semibold text-ink transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:cursor-not-allowed disabled:opacity-40"
      >
        Send
      </button>
    </form>
  );
}
