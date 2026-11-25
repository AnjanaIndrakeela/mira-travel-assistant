import Image from "next/image";

import { brand } from "@/lib/brand";

type Props = { onStartOver?: () => void; showStartOver?: boolean; canStartOver?: boolean };

/** Mira's mark and name, what she is and whose she is, and a "New chat" action. Mobile first. */
export function Header({ onStartOver, showStartOver = false, canStartOver = true }: Props) {
  return (
    <header className="sticky top-0 z-10 border-b border-line/70 bg-surface/80 shadow-[0_1px_0_rgba(255,255,255,0.9)_inset,0_8px_24px_-18px_rgba(17,17,17,0.35)] backdrop-blur-md">
      <div className="mx-auto flex min-h-16 max-w-3xl items-center justify-between gap-3 px-4 py-2 lg:max-w-6xl 2xl:max-w-7xl">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 rounded-full shadow-[0_6px_14px_-6px_rgba(242,107,29,0.55)]">
            <Image src="/mira-avatar.png" alt="" width={44} height={44} priority className="h-11 w-11 rounded-full" />
          </span>
          <div className="min-w-0 leading-tight">
            <h1 className="text-brand-lg font-extrabold uppercase tracking-[0.14em] text-ink">
              {brand.assistantName}
            </h1>
            <p className="text-brand-xs text-muted">
              <span className="font-medium text-ink/80">Intelligent Travel Booking Assistant</span>
              <span className="hidden sm:inline"> - </span>
              <span className="block sm:inline">
                <span className="font-semibold text-brand-orange">{brand.name}</span>
              </span>
            </p>
          </div>
        </div>
        {showStartOver && onStartOver && (
          <button
            type="button"
            onClick={onStartOver}
            disabled={!canStartOver}
            title={canStartOver ? "Start a new chat" : "Wait for Mira's reply, then start a new chat"}
            className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-button border border-line bg-gradient-to-b from-white to-[#F5F5F5] px-3 py-1.5 text-brand-xs font-semibold text-ink shadow-[0_1px_0_#fff_inset,0_2px_6px_-2px_rgba(17,17,17,0.18)] transition-colors hover:border-ink focus-visible:outline-2 focus-visible:outline-brand-orange disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-line"
          >
            <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M8 3v10M3 8h10" />
            </svg>
            New chat
          </button>
        )}
      </div>
    </header>
  );
}
