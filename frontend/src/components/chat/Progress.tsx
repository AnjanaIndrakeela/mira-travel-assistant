// What Mira is doing right now, in four plain stages driven by the graph steps the stream
// reports (AG-UI-style STEP events). Real progress, not a timer: a stage ticks only when the
// server has finished it.

export const STAGES = ["Reading your message", "Checking tours, prices and policies", "Writing the reply", "Adding cards and photos"] as const;

/** The stage in progress once a graph step has finished. */
const NEXT_STAGE: Record<string, number> = {
  load_visitor: 0, guard: 0,
  discovery: 1, route: 1,
  retrieve: 2, price: 2, match_tours: 2,
  respond: 3, persist: 3,
  build_ui: 4,
};

/** Index of the stage in progress, given the last finished graph step (null = just started). */
export const stageOf = (node: string | null): number => (node ? (NEXT_STAGE[node] ?? 0) : 0);

export function Stages({ current, compact = false }: { current: number; compact?: boolean }) {
  return (
    <ol className={`flex ${compact ? "flex-wrap gap-x-3 gap-y-1" : "flex-col gap-2"}`} aria-label="Progress">
      {STAGES.map((s, i) => {
        const state = i < current ? "done" : i === current ? "now" : "todo";
        return (
          <li key={s} className="flex items-center gap-2 text-brand-xs" aria-current={state === "now" ? "step" : undefined}>
            <span
              aria-hidden
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                state === "done" ? "bg-accent-leaf text-brand-white" : state === "now" ? "animate-pulse bg-brand-orange" : "border border-line"
              }`}
            >
              {state === "done" ? "✓" : ""}
            </span>
            <span className={state === "todo" ? "text-muted" : state === "now" ? "font-semibold" : ""}>
              {s}
              <span className="sr-only">{state === "done" ? " (done)" : state === "now" ? " (in progress)" : ""}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** A placeholder reply while Mira works, so the page shows where the answer will land. */
export function ReplySkeleton() {
  return (
    <div aria-hidden className="flex w-full max-w-md animate-pulse flex-col gap-2 rounded-card border border-line px-4 py-3">
      <div className="h-3 w-11/12 rounded bg-line" />
      <div className="h-3 w-4/5 rounded bg-line" />
      <div className="h-3 w-3/5 rounded bg-line" />
    </div>
  );
}
