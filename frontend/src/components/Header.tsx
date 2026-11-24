import { brand } from "@/lib/brand";

type Props = { onStartOver?: () => void; showStartOver?: boolean; canStartOver?: boolean };

/** Text logo (the dataset has no logo file) and a "New chat" action. Mobile first. */
export function Header({ onStartOver, showStartOver = false, canStartOver = true }: Props) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-3xl items-center lg:max-w-6xl 2xl:max-w-7xl justify-between gap-3 px-4">
        <div className="flex min-w-0 items-center gap-2">
          <span aria-hidden className="h-6 w-6 shrink-0 rounded-full bg-brand-orange" />
          <div className="min-w-0 leading-tight">
            <p className="truncate text-brand-sm font-bold">{brand.name}</p>
            <p className="text-brand-xs text-muted">Chat with {brand.assistantName}, your travel assistant</p>
          </div>
        </div>
        {showStartOver && onStartOver && (
          <button
            type="button"
            onClick={onStartOver}
            disabled={!canStartOver}
            title={canStartOver ? "Start a new chat" : "Wait for Mira's reply, then start a new chat"}
            className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-button border border-line px-3 py-1.5 text-brand-xs font-semibold text-ink transition-colors hover:border-ink focus-visible:outline-2 focus-visible:outline-brand-orange disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-line"
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
