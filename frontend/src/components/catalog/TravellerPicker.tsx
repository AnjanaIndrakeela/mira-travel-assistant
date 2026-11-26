"use client";

import { useState } from "react";

import type { ComponentOf } from "@/lib/catalog-schema";

import type { Actions } from "./registry";
import { Card, INPUT, Pill } from "./ui";

type Props = ComponentOf<"traveller_picker"> & { actions: Actions };

function Stepper({ label, value, min, max, onChange }: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (n: number) => void;
}) {
  const btn =
    "flex h-9 w-9 items-center justify-center rounded-full bg-surface text-brand-lg font-semibold text-ink shadow-sm ring-1 ring-line transition-all hover:ring-brand-orange active:scale-95 disabled:opacity-35 disabled:hover:ring-line";
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-ink/[0.03] py-1.5 pl-3 pr-1.5">
      <span className="text-brand-md font-medium">{label}</span>
      <div className="flex items-center gap-1.5 rounded-full bg-ink/[0.04] p-1">
        <button type="button" className={btn} aria-label={`Fewer ${label.toLowerCase()}`}
          disabled={value <= min} onClick={() => onChange(value - 1)}>
          −
        </button>
        <span className="w-7 text-center text-brand-md font-bold tabular-nums" aria-live="polite">{value}</span>
        <button type="button" className={btn} aria-label={`More ${label.toLowerCase()}`}
          disabled={value >= max} onClick={() => onChange(value + 1)}>
          +
        </button>
      </div>
    </div>
  );
}

/** Who is travelling: adults +/- and an age for each child. Sends a plain, structured message. */
export function TravellerPicker({ adults: startAdults, child_ages, ask_child_ages, actions }: Props) {
  const [adults, setAdults] = useState(startAdults);
  const [ages, setAges] = useState<(number | null)[]>(
    child_ages.length ? child_ages : ask_child_ages ? [null] : [],
  );
  const [sent, setSent] = useState(false);
  const missingAge = ages.some((a) => a === null);

  function setChildren(n: number) {
    setAges((prev) => (n > prev.length ? [...prev, null] : prev.slice(0, n)));
  }

  function send() {
    const known = ages.filter((a): a is number => a !== null);
    const people = `${adults} adult${adults === 1 ? "" : "s"}`;
    const kids = known.length
      ? ` and ${known.length} child${known.length === 1 ? "" : "ren"} aged ${known.join(", ")}`
      : " and no children";
    setSent(true);
    actions.act(
      { name: "set_travellers", context: { adults, child_ages: known }, component: "TravellerPicker" },
      `We are ${people}${kids}.`,
    );
  }

  const locked = sent || !actions.latest;
  return (
    <Card label="Who is travelling" accent="sky" icon="users" title="Who is travelling?" subtitle="Children are priced by age">
      <fieldset disabled={locked} className="flex flex-col gap-2">
        <Stepper label="Adults" value={adults} min={1} max={20} onChange={setAdults} />
        <Stepper label="Children" value={ages.length} min={0} max={10} onChange={setChildren} />
        {ages.map((age, i) => (
          <label key={i} className="flex items-center justify-between gap-3 pl-3 text-brand-sm">
            <span className="text-muted">Child {i + 1} age</span>
            <select
              value={age ?? ""}
              onChange={(e) => setAges((prev) => prev.map((a, j) => (j === i ? Number(e.target.value) : a)))}
              className={`min-h-10 max-w-32 ${INPUT} ${age === null ? "border-brand-orange/60" : "border-line"}`}
            >
              <option value="" disabled>
                Choose
              </option>
              {Array.from({ length: 18 }, (_, n) => (
                <option key={n} value={n}>
                  {n === 0 ? "Under 1" : n}
                </option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>
      {missingAge && !locked && <p className="text-brand-xs text-muted">Child ages decide the price, so please add each one.</p>}
      <div>
        <Pill onClick={send} icon={sent ? "check" : "arrow"} disabled={locked || missingAge || actions.busy}>
          {sent ? "Sent" : "Use these travellers"}
        </Pill>
      </div>
    </Card>
  );
}
