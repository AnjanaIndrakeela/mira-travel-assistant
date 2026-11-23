"use client";

import { useState } from "react";

import { ApiError, book, type BookingResult } from "@/lib/api";
import type { ComponentOf } from "@/lib/catalog-schema";

import type { Actions } from "./registry";
import { Card, Field, Pill } from "./ui";

type Props = ComponentOf<"booking_form"> & { actions: Actions };

/**
 * Mock booking (11.11). The form posts straight to /bookings: the details never go through
 * the chat, the LLM or the traces, and the card number is never stored.
 */
export function BookingForm({ quote_id, fields, actions }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [card, setCard] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<BookingResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      const res = await book(quote_id, { name: name.trim(), email: email.trim(), ...(phone.trim() ? { phone: phone.trim() } : {}) }, card);
      setResult(res);
      if (res.status !== "confirmed") setCard("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Nothing was charged.");
    } finally {
      setSending(false);
    }
  }

  if (result?.status === "confirmed") {
    return (
      <Card label="Booking confirmed" accent="leaf" wide>
        <h3 className="text-brand-md font-semibold">Booking confirmed</h3>
        <p className="text-brand-sm" role="status">{result.message}</p>
        {result.payment_reference && <p className="text-brand-xs text-muted">Reference {result.payment_reference}</p>}
      </Card>
    );
  }

  if (!open) {
    return (
      <div>
        <Pill onClick={() => setOpen(true)}>Book this trip</Pill>
      </div>
    );
  }

  return (
    <Card label="Book this trip" accent="sun" wide>
      <h3 className="text-brand-md font-semibold">Book this trip</h3>
      {result && (
        <div role="alert" className="flex flex-col gap-2 rounded-input border border-accent-coral p-3 text-brand-sm">
          <p>{result.message}</p>
          {result.next_steps.includes("new_quote") && (
            <div>
              <Pill variant="outline" disabled={actions.busy} onClick={() => actions.send("Please give me a new quote for this trip.")}>
                Get a new quote
              </Pill>
            </div>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="rounded-input border border-accent-coral p-3 text-brand-sm">
          {error}
        </p>
      )}
      {result?.status !== "price_changed" && (
        <form onSubmit={submit} className="flex flex-col gap-3">
          {fields.includes("name") && (
            <Field label="Full name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="name" />
          )}
          {fields.includes("email") && (
            <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} autoComplete="email" />
          )}
          {fields.includes("phone") && (
            <Field label="Phone (optional)" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} autoComplete="tel" />
          )}
          {fields.includes("card_number") && (
            <Field
              label="Card number (demo)"
              inputMode="numeric"
              autoComplete="off"
              value={card}
              onChange={(e) => setCard(e.target.value)}
              required
              minLength={12}
              maxLength={23}
              hint="Demo payment only, nothing is charged. Use 4242 4242 4242 4242 (works) or 4000 0000 0000 0002 (fails)."
            />
          )}
          <div className="flex flex-wrap gap-2">
            <Pill type="submit" disabled={sending}>
              {sending ? "Booking…" : result ? "Try again" : "Pay deposit and book"}
            </Pill>
            <Pill variant="outline" onClick={() => setOpen(false)} disabled={sending}>
              Not now
            </Pill>
          </div>
        </form>
      )}
    </Card>
  );
}
