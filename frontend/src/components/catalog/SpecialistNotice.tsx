"use client";

import { useState } from "react";

import { ApiError, sendEnquiry } from "@/lib/api";
import type { ComponentOf } from "@/lib/catalog-schema";

import { brand } from "@/lib/brand";

import { Card, Field, Icon, INPUT, Pill } from "./ui";

type Props = ComponentOf<"specialist_notice">;

const TITLES: Record<Props["reason"], string> = {
  no_price: "A specialist will confirm the price",
  custom_request: "Our team can plan this for you",
  custom_plan: "Want a plan made for you?",
  unanswered_question: "Our team can answer this",
  handoff: "A travel specialist will help",
  booking_failed: "Our team will send a payment link",
};

/** No price or no answer: a specialist takes over. Contact details go straight to /enquiries. */
export function SpecialistNotice({ reason, message, enquiry_id, summary }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState(summary ?? "");
  const plan = reason === "custom_plan";
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
    <Card label={TITLES[reason]} accent={plan ? "sun" : "coral"} wide icon={plan ? "route" : "chat"}
      title={TITLES[reason]} subtitle={`Real people at ${brand.name}`}>
      <p className="text-brand-sm leading-relaxed">{message}</p>
      {enquiry_id && !done && (
        <p className="flex items-center gap-1.5 text-brand-xs text-muted">
          <Icon name="check" className="h-3.5 w-3.5 text-accent-leaf" />
          We&apos;ve noted this for our team.
        </p>
      )}
      {done ? (
        <p className="flex items-start gap-2 rounded-lg bg-accent-leaf/10 px-3 py-2.5 text-brand-sm font-semibold" role="status">
          <Icon name="check" className="mt-0.5 h-4 w-4 text-accent-leaf" />
          {done}
        </p>
      ) : open ? (
        <form onSubmit={submit} className="flex flex-col gap-3 rounded-lg bg-ink/[0.025] p-3">
          <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="name" />
          <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} autoComplete="email" />
          <label className="flex flex-col gap-1.5 text-brand-sm">
            <span className="font-medium text-ink/80">{plan ? "Your trip (edit as you like)" : "Anything we should know? (optional)"}</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={2000}
              rows={3}
              className={`${INPUT} border-line`}
            />
          </label>
          {error && <p role="alert" className="text-brand-sm text-accent-coral">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Pill type="submit" icon="arrow" disabled={sending}>{sending ? "Sending…" : "Send to our team"}</Pill>
            <Pill variant="outline" onClick={() => setOpen(false)} disabled={sending}>Cancel</Pill>
          </div>
        </form>
      ) : (
        <div>
          <Pill onClick={() => setOpen(true)} variant={plan ? "outline" : "primary"} icon="arrow">
            {plan ? "Send a custom plan request" : "Ask a specialist to contact me"}
          </Pill>
        </div>
      )}
    </Card>
  );
}
