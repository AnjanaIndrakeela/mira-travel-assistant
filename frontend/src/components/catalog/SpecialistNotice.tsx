"use client";

import { useState } from "react";

import { ApiError, sendEnquiry } from "@/lib/api";
import type { ComponentOf } from "@/lib/catalog-schema";

import { Card, Field, Pill } from "./ui";

type Props = ComponentOf<"specialist_notice">;

const TITLES: Record<Props["reason"], string> = {
  no_price: "A specialist will confirm the price",
  custom_request: "Our team can plan this for you",
  unanswered_question: "Our team can answer this",
  handoff: "A travel specialist will help",
  booking_failed: "Our team will send a payment link",
};

/** No price or no answer: a specialist takes over. Contact details go straight to /enquiries. */
export function SpecialistNotice({ reason, message, enquiry_id }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      const res = await sendEnquiry({
        kind: reason === "no_price" ? "no_price" : "custom",
        notes: notes.trim() || undefined,
        contact: { name: name.trim(), email: email.trim() },
      });
      setDone(res.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <Card label={TITLES[reason]} accent="coral" wide>
      <h3 className="text-brand-md font-semibold">{TITLES[reason]}</h3>
      <p className="text-brand-sm">{message}</p>
      {enquiry_id && !done && <p className="text-brand-xs text-muted">We&apos;ve noted this for our team.</p>}
      {done ? (
        <p className="text-brand-sm font-semibold" role="status">{done}</p>
      ) : open ? (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="name" />
          <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} autoComplete="email" />
          <label className="flex flex-col gap-1 text-brand-sm">
            <span className="font-semibold">Anything we should know? (optional)</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={2000}
              rows={3}
              className="rounded-input border border-line px-3 py-2 text-brand-md outline-none focus:border-brand-orange"
            />
          </label>
          {error && <p role="alert" className="text-brand-sm text-accent-coral">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Pill type="submit" disabled={sending}>{sending ? "Sending…" : "Send to our team"}</Pill>
            <Pill variant="outline" onClick={() => setOpen(false)} disabled={sending}>Cancel</Pill>
          </div>
        </form>
      ) : (
        <div>
          <Pill onClick={() => setOpen(true)}>Ask a specialist to contact me</Pill>
        </div>
      )}
    </Card>
  );
}
