import type { ComponentOf } from "@/lib/catalog-schema";

import { Card } from "./ui";

/** R2: a returning visitor's last trip, shown above Mira's message. A still-valid price comes
 * as its own price_breakdown card under the message. Without a trip (they chatted before but
 * never got a price) it is just a greeting. */
export function WelcomeBack({ tour_title }: ComponentOf<"welcome_back">) {
  return (
    <div className="flex flex-col gap-3">
      <Card
        label="Welcome back"
        accent="teal"
        icon="sparkle"
        title="Welcome back"
        subtitle={tour_title ? "Picking up where you left off" : "A new chat, ready when you are"}
      >
        <p className="text-brand-sm">
          {tour_title ? (
            <>
              Last time you looked at the <span className="font-semibold">{tour_title}</span>.
            </>
          ) : (
            "Good to see you again."
          )}
        </p>
      </Card>
    </div>
  );
}
