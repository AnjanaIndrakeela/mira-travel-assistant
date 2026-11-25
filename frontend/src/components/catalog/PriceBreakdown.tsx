"use client";

import { useEffect, useState } from "react";
import { z } from "zod";

import { getQuote, type PublicQuote } from "@/lib/api";

import { Card, Chip, Icon, niceDate, shortDate, usd } from "./ui";

// What /quotes/{id} must look like. strictObject: if a cost or margin field ever appeared,
// the card would refuse to show anything rather than show it.
const PublicQuoteSchema = z.strictObject({
  tour_id: z.string(),
  tour_name: z.string(),
  start_date: z.string(),
  end_date: z.string(),
  adults: z.number().int(),
  children: z.number().int(),
  infants: z.number().int(),
  price_usd: z.number().int().positive(),
  deposit_usd: z.number().int().positive(),
  balance_usd: z.number().int().nonnegative(),
  balance_due: z.string().nullable(),
  currency: z.literal("USD"),
});

function who(q: PublicQuote) {
  const parts = [`${q.adults} adult${q.adults === 1 ? "" : "s"}`];
  if (q.children) parts.push(`${q.children} child${q.children === 1 ? "" : "ren"}`);
  if (q.infants) parts.push(`${q.infants} infant${q.infants === 1 ? "" : "s"} (free)`);
  return parts.join(", ");
}

/** Holds only a quote ID; the numbers are fetched from the verified quote (11.10). */
export function PriceBreakdown({ quote_id }: { quote_id: string }) {
  const [quote, setQuote] = useState<PublicQuote | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    getQuote(quote_id)
      .then((raw) => {
        const parsed = PublicQuoteSchema.safeParse(raw);
        if (!alive) return;
        if (parsed.success) setQuote(parsed.data);
        else setFailed(true);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [quote_id]);

  if (failed) {
    return (
      <Card label="Price" icon="tag" title="Your price">
        <p className="text-brand-sm text-muted">I couldn&apos;t load the price card. The price in my message above is the verified one.</p>
      </Card>
    );
  }
  if (!quote) {
    return (
      <Card label="Price" icon="tag" title="Your price" subtitle="Loading your price…">
        <div role="status" aria-label="Loading your price" className="flex flex-col gap-2">
          <div className="h-16 animate-pulse rounded-lg bg-ink/[0.05]" />
          <div className="h-3 w-2/3 animate-pulse rounded-full bg-ink/[0.05]" />
        </div>
      </Card>
    );
  }
  const oneDay = quote.start_date === quote.end_date;
  const split = quote.balance_usd > 0;
  const share = Math.max(4, Math.round((quote.deposit_usd / quote.price_usd) * 100));
  return (
    <Card label="Your price" accent="leaf" icon="tag" title="Your price" subtitle={quote.tour_name}>
      <div className="flex flex-wrap gap-1.5">
        <Chip icon="calendar">
          {oneDay ? shortDate(quote.start_date) : `${shortDate(quote.start_date)} – ${shortDate(quote.end_date)}`}
        </Chip>
        <Chip icon="users">{who(quote)}</Chip>
      </div>

      <div className="rounded-lg bg-gradient-to-br from-accent-leaf/12 via-accent-leaf/[0.04] to-transparent px-4 py-3">
        <p className="text-brand-xs font-medium uppercase tracking-wider text-muted">Total</p>
        <p className="text-brand-xl font-bold leading-tight tracking-tight">{usd(quote.price_usd)}</p>
        <p className="text-brand-xs text-muted">for everyone travelling</p>
      </div>

      {split ? (
        <div className="flex flex-col gap-2">
          <div
            className="flex h-2 overflow-hidden rounded-full bg-ink/[0.07]"
            role="img"
            aria-label={`Deposit ${usd(quote.deposit_usd)} now, balance ${usd(quote.balance_usd)} later`}
          >
            <span className="rounded-full bg-brand-orange" style={{ width: `${share}%` }} />
          </div>
          <dl className="grid grid-cols-2 gap-3 text-brand-sm">
            <div>
              <dt className="flex items-center gap-1.5 text-brand-xs text-muted">
                <span aria-hidden className="h-2 w-2 rounded-full bg-brand-orange" />
                Deposit to book
              </dt>
              <dd className="font-semibold">{usd(quote.deposit_usd)}</dd>
            </div>
            <div className="text-right">
              <dt className="flex items-center justify-end gap-1.5 text-brand-xs text-muted">
                <span aria-hidden className="h-2 w-2 rounded-full bg-ink/20" />
                Balance
              </dt>
              <dd className="font-semibold">{usd(quote.balance_usd)}</dd>
              {quote.balance_due && <dd className="text-brand-xs text-muted">due by {niceDate(quote.balance_due)}</dd>}
            </div>
          </dl>
        </div>
      ) : (
        <dl className="flex items-center justify-between gap-3 rounded-lg border border-line/80 px-3 py-2 text-brand-sm">
          <dt className="text-muted">Paid in full when you book</dt>
          <dd className="font-semibold">{usd(quote.deposit_usd)}</dd>
        </dl>
      )}

      <p className="flex items-center gap-1.5 text-brand-xs text-muted">
        <Icon name="shield" className="h-3.5 w-3.5 text-accent-leaf" />
        From our rate sheet · quote {quote_id.slice(0, 8)}
      </p>
    </Card>
  );
}
