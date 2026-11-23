import type { ComponentOf } from "@/lib/catalog-schema";

import { PriceBreakdown } from "./PriceBreakdown";
import { Card } from "./ui";

/** R2: a returning visitor's last trip; the price (if still valid) is fetched by quote ID. */
export function WelcomeBack({ tour_title, quote_id }: ComponentOf<"welcome_back">) {
  return (
    <div className="flex flex-col gap-3">
      <Card label="Welcome back" accent="teal">
        <h3 className="text-brand-md font-semibold">Welcome back</h3>
        <p className="text-brand-sm">Last time you looked at the {tour_title}.</p>
      </Card>
      {quote_id && <PriceBreakdown quote_id={quote_id} />}
    </div>
  );
}
