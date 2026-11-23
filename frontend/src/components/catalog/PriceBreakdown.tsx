"use client";

import { useEffect, useState } from "react";
import { z } from "zod";

import { getQuote, type PublicQuote } from "@/lib/api";

import { Card, niceDate, usd } from "./ui";

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
      <Card label="Price">
        <p className="text-brand-sm text-muted">I couldn&apos;t load the price card. The price in my message above is the verified one.</p>
      </Card>
    );
  }
  if (!quote) {
    return (
      <Card label="Price">
        <p className="text-brand-sm text-muted" role="status">Loading your price…</p>
      </Card>
    );
  }
  const oneDay = quote.start_date === quote.end_date;
  return (
    <Card label="Your price" accent="leaf">
      <div>
        <h3 className="text-brand-md font-semibold">{quote.tour_name}</h3>
        <p className="text-brand-sm text-muted">
          {oneDay ? niceDate(quote.start_date) : `${niceDate(quote.start_date)} to ${niceDate(quote.end_date)}`} · {who(quote)}
        </p>
      </div>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-brand-sm">
        <dt className="font-semibold">Total</dt>
        <dd className="text-right text-brand-lg font-bold">{usd(quote.price_usd)}</dd>
        {quote.balance_usd > 0 ? (
          <>
            <dt>Deposit to book</dt>
            <dd className="text-right font-semibold">{usd(quote.deposit_usd)}</dd>
            <dt>Balance</dt>
            <dd className="text-right">{usd(quote.balance_usd)}</dd>
            {quote.balance_due && (
              <>
                <dt>Balance due by</dt>
                <dd className="text-right">{niceDate(quote.balance_due)}</dd>
              </>
            )}
          </>
        ) : (
          <>
            <dt>Paid when you book</dt>
            <dd className="text-right font-semibold">{usd(quote.deposit_usd)}</dd>
          </>
        )}
      </dl>
      <p className="text-brand-xs text-muted">From our rate sheet. Quote {quote_id.slice(0, 8)}.</p>
    </Card>
  );
}
