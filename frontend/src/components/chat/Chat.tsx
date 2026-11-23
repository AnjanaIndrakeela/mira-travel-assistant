"use client";

import { useCallback, useEffect, useState } from "react";

import { Header } from "@/components/Header";
import { ApiError, FIRST_STEP, ids, loadHistory, STEP_LABELS, streamChat } from "@/lib/api";
import { brand } from "@/lib/brand";

import { Composer } from "./Composer";
import { AssistantMessage, type ChatItem, MessageList } from "./Messages";

// Fixed text, not the LLM: shown before the first message, so it costs nothing and never fails.
const WELCOME = `Hello, I'm ${brand.assistantName}. I can suggest tours, answer questions about them and our policies, and give you an instant price.`;
const STARTERS = [
  "How much is the Sigiriya and Minneriya day tour for 2 adults on 10 January 2027?",
  "We'd like a week of culture and wildlife. What do you suggest?",
  "What's your cancellation policy?",
];

type Failure = { message: string; retryable: boolean; text: string };

let counter = 0;
const nextId = () => `m${Date.now().toString(36)}${(counter++).toString(36)}`;

export function Chat() {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [thinking, setThinking] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Restore the current conversation after a reload (the server keeps it per conversation ID).
  useEffect(() => {
    let alive = true;
    loadHistory().then((history) => {
      if (!alive) return;
      setItems(history.map((m) => ({ id: nextId(), role: m.role, text: m.text })));
      setLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  // Scroll to the very end of the page, so the newest item clears the sticky input bar.
  useEffect(() => {
    window.scrollTo({ top: document.documentElement.scrollHeight });
  }, [items, thinking, failure]);

  const ask = useCallback(async (text: string, isRetry = false) => {
    setFailure(null);
    if (!isRetry) setItems((prev) => [...prev, { id: nextId(), role: "traveller", text }]);
    setThinking(true);
    try {
      setStep(FIRST_STEP);
      // AG-UI-style stream: progress per graph step, then the reply and its components
      const res = await streamChat(text, (node) => setStep(STEP_LABELS[node] ?? null));
      setItems((prev) => [...prev, { id: nextId(), role: "mira", text: res.message, ui: res.ui }]);
    } catch (err) {
      const e = err instanceof ApiError ? err : new ApiError("Something went wrong. Please try again.", true);
      setFailure({ message: e.message, retryable: e.retryable, text });
    } finally {
      setThinking(false);
    }
  }, []);

  function startOver() {
    ids.startOver();
    setItems([]);
    setFailure(null);
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <Header onStartOver={startOver} canStartOver={items.length > 0 && !thinking} />

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 pb-4 pt-5">
        <div className="flex flex-1 flex-col gap-4">
          <AssistantMessage text={WELCOME} />

          {loaded && items.length === 0 && (
            <div className="flex flex-col gap-2 pl-9.5" aria-label="Suggestions">
              <p className="text-brand-xs text-muted">Try one of these, or ask in your own words:</p>
              <div className="flex flex-wrap gap-2">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => ask(s)}
                    className="rounded-button border border-line px-3 py-1.5 text-left text-brand-sm transition-colors hover:border-brand-orange focus-visible:outline-2 focus-visible:outline-brand-orange"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <MessageList items={items} thinking={thinking} step={step} send={(t) => ask(t)} />

          {failure && (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-accent-coral bg-surface px-4 py-3"
            >
              <p className="text-brand-sm">{failure.message}</p>
              {failure.retryable && (
                <button
                  type="button"
                  onClick={() => ask(failure.text, true)}
                  className="rounded-button bg-brand-orange px-4 py-1.5 text-brand-sm font-semibold text-ink hover:opacity-90"
                >
                  Try again
                </button>
              )}
            </div>
          )}
        </div>
      </main>

      <div className="sticky bottom-0 border-t border-line bg-surface">
        <div className="mx-auto max-w-3xl px-4 py-3">
          <Composer onSend={(t) => ask(t)} disabled={thinking} />
          <p className="mt-1.5 text-center text-brand-xs text-muted">
            Prices come from our rate sheet. A travel specialist confirms anything Mira can&apos;t.
          </p>
        </div>
      </div>
    </div>
  );
}
