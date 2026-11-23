import { brand } from "@/lib/brand";

type Props = { onStartOver?: () => void; canStartOver?: boolean };

/** Text logo (the dataset has no logo file) and a "Start over" action. Mobile first. */
export function Header({ onStartOver, canStartOver = false }: Props) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-3xl items-center justify-between gap-3 px-4">
        <div className="flex min-w-0 items-center gap-2">
          <span aria-hidden className="h-6 w-6 shrink-0 rounded-full bg-brand-orange" />
          <div className="min-w-0 leading-tight">
            <p className="truncate text-brand-sm font-bold">{brand.name}</p>
            <p className="text-brand-xs text-muted">Chat with {brand.assistantName}, your travel assistant</p>
          </div>
        </div>
        {canStartOver && onStartOver && (
          <button
            type="button"
            onClick={onStartOver}
            className="shrink-0 rounded-button border border-line px-3 py-1.5 text-brand-xs font-semibold text-ink transition-colors hover:border-ink focus-visible:outline-2 focus-visible:outline-brand-orange"
          >
            Start over
          </button>
        )}
      </div>
    </header>
  );
}
