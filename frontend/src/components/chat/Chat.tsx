"use client";

import { useCallback, useEffect, useState } from "react";

import { Header } from "@/components/Header";
import {
  ApiError, FIRST_STEP, type HistoryMessage, ids, loadHistory, loadWelcome, STEP_LABELS, streamChat,
} from "@/lib/api";
import { brand } from "@/lib/brand";

import { Composer } from "./Composer";
import { stageOf } from "./Progress";
import { TripPanel } from "./TripPanel";
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

/** A saved message as a chat item: Mira's replies come back with their cards, a specialist's as written. */
const toItem = (m: HistoryMessage): ChatItem =>
  m.role === "mira"
    ? { id: nextId(), role: "mira", text: m.text, ui: m.ui ?? [] }
    : { id: nextId(), role: m.role, text: m.text };

export function Chat() {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [thinking, setThinking] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const [node, setNode] = useState<string | null>(null); // last finished graph step
  const [failure, setFailure] = useState<Failure | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [returning, setReturning] = useState(false);

  // A new chat for a returning visitor (R2): their last trip, re-priced today by the server.
  const welcomeBack = useCallback(async (isAlive: () => boolean = () => true) => {
    const w = await loadWelcome();
    if (!w || !isAlive()) return;
    setItems([{ id: nextId(), role: "mira", text: w.message, ui: w.ui }]);
    setReturning(true);
  }, []);

  // Restore the current conversation after a reload (the server keeps it per conversation ID).
  // A link from a specialist's email (?chat=<id>) opens that chat, then the address is tidied.
  useEffect(() => {
    let alive = true;
    const linked = new URLSearchParams(window.location.search).get("chat");
    if (linked) {
      ids.openConversation(linked);
      window.history.replaceState(null, "", window.location.pathname);
    }
    loadHistory().then(async (history) => {
      if (!alive) return;
      setItems(history.map(toItem));
      if (history.length === 0) await welcomeBack(() => alive);
      if (alive) setLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, [welcomeBack]);

  // Back on this tab: if a specialist has replied since, show it (no need to reload the page).
  useEffect(() => {
    async function check() {
      if (document.visibilityState !== "visible" || thinking || !ids.conversation()) return;
      const history = await loadHistory();
      const count = (list: { role: string }[]) => list.filter((m) => m.role === "specialist").length;
      if (count(history) > count(items)) setItems(history.map(toItem));
    }
    document.addEventListener("visibilitychange", check);
    window.addEventListener("focus", check);
    return () => {
      document.removeEventListener("visibilitychange", check);
      window.removeEventListener("focus", check);
    };
  }, [items, thinking]);

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
      setNode(null);
      // AG-UI-style stream: progress per graph step, then the reply and its components
      const res = await streamChat(text, (n) => {
        setStep(STEP_LABELS[n] ?? null);
        setNode(n);
      });
      setItems((prev) => [...prev, { id: nextId(), role: "mira", text: res.message, ui: res.ui }]);
    } catch (err) {
      const e = err instanceof ApiError ? err : new ApiError("Something went wrong. Please try again.", true);
      setFailure({ message: e.message, retryable: e.retryable, text });
    } finally {
      setThinking(false);
    }
  }, []);

  // "New chat": a clean thread. The old chat is deleted on the server; a new conversation
  // starts with the next message.
  // (The "welcome back" with the last trip is for opening the site, not for a new chat.)
  function startOver() {
    ids.startOver();
    setItems([]);
    setFailure(null);
    setReturning(false);
    setStep(null);
    setNode(null);
    window.scrollTo({ top: 0 });
  }

  // "Start fresh": forget the visitor too, so the party and last trip aren't reused.
  function startFresh() {
    ids.forgetVisitor();
    setItems([]);
    setFailure(null);
    setReturning(false);
  }

  const onlyWelcome = returning && items.length === 1;

  return (
    <div className="flex min-h-dvh flex-col">
      <Header onStartOver={startOver} showStartOver={items.length > 0 || thinking} canStartOver={!thinking} />

      <main className="mx-auto grid w-full max-w-3xl flex-1 grid-cols-1 items-start gap-8 px-4 pb-4 pt-5 lg:max-w-6xl lg:grid-cols-[minmax(0,1fr)_18rem] 2xl:max-w-7xl 2xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <AssistantMessage text={WELCOME} />

          {loaded && (items.length === 0 || onlyWelcome) && (
            <div className="flex flex-col gap-2 pl-11.5" aria-label="Suggestions">
              <p className="text-brand-xs text-muted">Try one of these, or ask in your own words:</p>
              <div className="flex flex-wrap gap-2">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => ask(s)}
                    className="min-h-11 rounded-button border border-white bg-gradient-to-b from-white to-[#F4F4F4] px-3.5 py-1.5 shadow-[0_1px_0_#fff_inset,0_6px_14px_-8px_rgba(17,17,17,0.35),0_0_0_1px_rgba(17,17,17,0.06)] text-left text-brand-sm transition-colors hover:border-brand-orange focus-visible:outline-2 focus-visible:outline-brand-orange"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <MessageList items={items} thinking={thinking} step={step} stage={stageOf(node)} send={(t) => ask(t)} />

          {onlyWelcome && !thinking && (
            <div className="flex flex-wrap items-center gap-2 pl-11.5">
              <button
                type="button"
                onClick={startFresh}
                className="min-h-11 rounded-button border border-white bg-gradient-to-b from-white to-[#F4F4F4] px-3.5 py-1.5 shadow-[0_1px_0_#fff_inset,0_6px_14px_-8px_rgba(17,17,17,0.35),0_0_0_1px_rgba(17,17,17,0.06)] text-brand-sm transition-colors hover:border-brand-orange focus-visible:outline-2 focus-visible:outline-brand-orange"
              >
                Start fresh
              </button>
              <span className="text-brand-xs text-muted">Forget my last trip and party on this device</span>
            </div>
          )}

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
                  className="min-h-11 rounded-button bg-brand-orange px-4 py-1.5 text-brand-sm font-semibold text-ink hover:opacity-90"
                >
                  Try again
                </button>
              )}
            </div>
          )}
        </div>

        <div className="hidden self-start lg:sticky lg:top-20 lg:block">
          <TripPanel items={items} thinking={thinking} stage={stageOf(node)} />
        </div>
      </main>

      <div className="sticky bottom-0 border-t border-line/70 bg-surface/85 shadow-[0_-10px_24px_-20px_rgba(17,17,17,0.4)] backdrop-blur-md">
        <div className="mx-auto max-w-3xl px-4 py-3 lg:max-w-6xl 2xl:max-w-7xl lg:pr-[calc(18rem+3rem)] 2xl:pr-[calc(20rem+3rem)]">
          <Composer onSend={(t) => ask(t)} disabled={thinking} />
          <p className="mt-1.5 text-center text-brand-xs text-muted">
            Prices come from our rate sheet. A travel specialist confirms anything Mira can&apos;t.
          </p>
        </div>
      </div>
    </div>
  );
}
