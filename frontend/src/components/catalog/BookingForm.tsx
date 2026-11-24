"use client";

import { useState } from "react";

import { ApiError, book, type BookingResult } from "@/lib/api";
import { BRANDS, brandInfo, type Brand, type CardField, checkCard, digitsOf, formatExpiry, formatNumber, guessBrand, TEST_CARDS, toPayload } from "@/lib/card";
import type { ComponentOf } from "@/lib/catalog-schema";

import type { Actions } from "./registry";
import { Card, Chip, Field, Icon, Pill } from "./ui";

type Props = ComponentOf<"booking_form"> & { actions: Actions };

/**
 * Mock booking and payment. It asks for everything a real checkout does (cardholder, card
 * type, number, expiry, security code), checks it here and again on the server, and posts
 * straight to /bookings: the details never go through the chat, the LLM or the traces, and
 * only the card type and last four digits are kept.
 */
export function BookingForm({ quote_id, fields, actions }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [holder, setHolder] = useState("");
  const [brand, setBrand] = useState<Brand>("visa");
  const [brandTouched, setBrandTouched] = useState(false);
  const [number, setNumber] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvc, setCvc] = useState("");
  const [errors, setErrors] = useState<Partial<Record<CardField, string>>>({});
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<BookingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const askCard = fields.includes("card");
  const info = brandInfo(brand);

  function clear(f: CardField) {
    if (errors[f]) setErrors((e) => ({ ...e, [f]: undefined }));
  }

  function onNumber(raw: string) {
    const guess = guessBrand(digitsOf(raw));
    const b = guess && !brandTouched ? guess : brand; // follow the number until a type is picked by hand
    if (b !== brand) setBrand(b);
    setNumber(formatNumber(raw, b));
    clear("number");
    clear("brand");
  }

  function fillTestCard(t: (typeof TEST_CARDS)[number]) {
    setBrand(t.brand);
    setNumber(t.number);
    setCvc(t.cvc);
    if (!expiry) setExpiry("12/30");
    if (!holder) setHolder(name || "Test Traveller");
    setErrors({});
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const card = { holder, brand, number, expiry, cvc };
    if (askCard) {
      const found = checkCard(card);
      setErrors(found);
      if (Object.keys(found).length) return;
    }
    setSending(true);
    try {
      const contact = { name: name.trim(), email: email.trim(), ...(phone.trim() ? { phone: phone.trim() } : {}) };
      const res = await book(quote_id, contact, toPayload(card));
      setResult(res);
      if (res.status !== "confirmed") {
        setCvc("");
        if (res.field) setErrors({ [res.field]: res.message.replace(/\s*Nothing was charged\.?/, "") });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Nothing was charged.");
    } finally {
      setSending(false);
    }
  }

  if (result?.status === "confirmed") {
    return (
      <Card label="Booking confirmed" accent="leaf" wide icon="check" title="Booking confirmed" subtitle="You're all set">
        <p className="text-brand-sm leading-relaxed" role="status">{result.message}</p>
        {(result.card || result.payment_reference) && (
          <div className="flex flex-wrap gap-1.5">
            {result.card && <Chip icon="card">Paid with {result.card}</Chip>}
            {result.payment_reference && <Chip icon="tag">Ref {result.payment_reference}</Chip>}
          </div>
        )}
      </Card>
    );
  }

  if (!open) {
    return (
      <div>
        <Pill onClick={() => setOpen(true)} icon="arrow">Book this trip</Pill>
      </div>
    );
  }

  return (
    <Card label="Book this trip" accent="sun" wide icon="card" title="Book this trip" subtitle="Secure your dates in a few steps">
      {result && !result.field && (
        <div role="alert" className="flex flex-col gap-2 rounded-lg border border-accent-coral/40 bg-accent-coral/[0.06] p-3 text-brand-sm">
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
        <p role="alert" className="rounded-lg border border-accent-coral/40 bg-accent-coral/[0.06] p-3 text-brand-sm">
          {error}
        </p>
      )}
      {result?.status !== "price_changed" && (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <fieldset className="flex flex-col gap-3">
            <legend className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
              <Icon name="user" className="h-3.5 w-3.5" />
              Your details
            </legend>
            {fields.includes("name") && (
              <Field label="Full name" name="name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="name" />
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              {fields.includes("email") && (
                <Field label="Email" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} autoComplete="email" />
              )}
              {fields.includes("phone") && (
                <Field label="Phone (optional)" name="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} autoComplete="tel" />
              )}
            </div>
          </fieldset>

          {askCard && (
            <fieldset className="flex min-w-0 flex-col gap-3 rounded-lg border border-line/80 bg-ink/[0.02] p-2.5 sm:p-3">
              <legend className="flex items-center gap-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
                <Icon name="card" className="h-3.5 w-3.5" />
                Card (demo payment)
              </legend>
              <p className="flex gap-2 rounded-lg bg-accent-sun/15 px-3 py-2 text-brand-xs">
                <Icon name="shield" className="mt-px h-3.5 w-3.5" />
                <span>This is a <strong>mock payment</strong>: no money moves and the card is never stored. Use a test card:</span>
              </p>
              <div className="flex flex-wrap gap-1.5" aria-label="Test cards">
                {TEST_CARDS.map((t) => (
                  <button
                    key={t.number}
                    type="button"
                    onClick={() => fillTestCard(t)}
                    className="min-h-9 rounded-full border border-line bg-surface px-3 text-brand-xs font-medium shadow-sm hover:border-brand-orange focus-visible:outline-2 focus-visible:outline-brand-orange"
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              <Field label="Name on card" name="cc-name" value={holder} error={errors.holder}
                onChange={(e) => { setHolder(e.target.value); clear("holder"); }}
                maxLength={80} autoComplete="off" />

              <div role="radiogroup" aria-label="Card type" className="flex flex-col gap-1 text-brand-sm">
                <span className="font-medium text-ink/80">Card type</span>
                <div className="grid grid-cols-[1fr_1.4fr_1fr] gap-1.5 sm:grid-cols-3">
                  {BRANDS.map((b) => (
                    <button
                      key={b.id}
                      type="button"
                      role="radio"
                      aria-checked={brand === b.id}
                      aria-label={b.name}
                      onClick={() => { setBrand(b.id); setBrandTouched(true); setNumber((n) => formatNumber(n, b.id)); clear("brand"); clear("cvc"); }}
                      className={`min-h-11 min-w-0 rounded-input border px-1 text-brand-xs font-semibold transition-all sm:px-2 sm:text-brand-sm ${brand === b.id ? "border-brand-orange bg-brand-orange/10 ring-4 ring-brand-orange/10" : "border-line bg-surface hover:border-ink/30"}`}
                    >
                      <span className="sm:hidden">{b.short}</span>
                      <span className="hidden sm:inline">{b.name}</span>
                    </button>
                  ))}
                </div>
                {errors.brand && <span className="text-brand-xs font-semibold text-accent-coral">{errors.brand}</span>}
              </div>

              <Field label="Card number" name="cc-number" value={number} error={errors.number}
                onChange={(e) => onNumber(e.target.value)}
                inputMode="numeric" autoComplete="off" placeholder={brand === "amex" ? "3782 822463 10005" : "4242 4242 4242 4242"}
                maxLength={23} />

              <div className="grid grid-cols-2 gap-3">
                <Field label="Expiry (MM/YY)" name="cc-exp" value={expiry} error={errors.expiry}
                  onChange={(e) => { setExpiry(formatExpiry(e.target.value, expiry)); clear("expiry"); }}
                  inputMode="numeric" autoComplete="off" placeholder="MM/YY" maxLength={5} />
                <Field label={brand === "amex" ? "CID (4 digits)" : "CVV (3 digits)"} name="cc-cvc" type="password" value={cvc} error={errors.cvc}
                  onChange={(e) => { setCvc(digitsOf(e.target.value).slice(0, info.cvc)); clear("cvc"); }}
                  inputMode="numeric" autoComplete="off" maxLength={info.cvc} />
              </div>
            </fieldset>
          )}

          <div className="flex flex-wrap gap-2">
            <Pill type="submit" icon="arrow" disabled={sending}>
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
