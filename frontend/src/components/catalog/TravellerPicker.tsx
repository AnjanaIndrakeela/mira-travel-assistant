"use client";

import { useState } from "react";

import type { ComponentOf } from "@/lib/catalog-schema";

import type { Actions } from "./registry";
import { Card, Pill } from "./ui";

type Props = ComponentOf<"traveller_picker"> & { actions: Actions };

function Stepper({ label, value, min, max, onChange }: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (n: number) => void;
}) {
  const btn =
    "flex h-10 w-10 items-center justify-center rounded-full border border-line text-brand-lg hover:border-brand-orange disabled:opacity-40";
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-brand-md">{label}</span>
      <div className="flex items-center gap-3">
        <button type="button" className={btn} aria-label={`Fewer ${label.toLowerCase()}`}
          disabled={value <= min} onClick={() => onChange(value - 1)}>
          −
        </button>
        <span className="w-6 text-center text-brand-md font-semibold" aria-live="polite">{value}</span>
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
    actions.send(`We are ${people}${kids}.`);
  }

  const locked = sent || !actions.latest;
  return (
    <Card label="Who is travelling" accent="sky">
      <h3 className="text-brand-md font-semibold">Who is travelling?</h3>
      <fieldset disabled={locked} className="flex flex-col gap-3">
        <Stepper label="Adults" value={adults} min={1} max={20} onChange={setAdults} />
        <Stepper label="Children" value={ages.length} min={0} max={10} onChange={setChildren} />
        {ages.map((age, i) => (
          <label key={i} className="flex items-center justify-between gap-3 text-brand-sm">
            <span>Child {i + 1} age</span>
            <select
              value={age ?? ""}
              onChange={(e) => setAges((prev) => prev.map((a, j) => (j === i ? Number(e.target.value) : a)))}
              className="min-h-10 rounded-input border border-line px-3 text-brand-md focus:border-brand-orange"
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
        <Pill onClick={send} disabled={locked || missingAge || actions.busy}>
          {sent ? "Sent" : "Use these travellers"}
        </Pill>
      </div>
    </Card>
  );
}
