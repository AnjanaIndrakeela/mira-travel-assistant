Extract the trip details the traveller has given so far, from the whole conversation. Today is {today}. Later messages override earlier ones.

Rules:
- "tour_mention": the tour name or ID as written ("the Cultural Triangle package", "T09"), or null.
- "start_date": the tour start date as YYYY-MM-DD, only when the traveller gave a specific day. Resolve relative dates ("next Friday", "12 April") against today; a date without a year means its next occurrence after today. A month or season alone ("sometime in March", "in the summer") is NOT a start date: leave "start_date" null. Null if not given.
- "travel_month": the month number (1-12) when they named a month but no specific day, else null.
- "adults": the number of adults, or null if not given. "Just me" = 1, "my partner and I" = 2, "a couple" = 2.
- "child_ages": the age of every child and infant mentioned, in years (a baby or infant under 1 = 0). Use [] if there are none. If a child is mentioned without an age, put "child_ages" in "missing".
- "traveller_type": "solo", "couple", "family" or "group" when clear, else null.
- "interests": short words for what they like ("beaches", "wildlife", "culture"), else [].
- "destinations": places in Sri Lanka they mention, else [].
- "days": how many days they want to travel, if said, else null.
- "missing": which of "tour", "start_date", "adults", "child_ages" are still needed for a quote.
Never invent a value that the traveller didn't give.

Conversation:
{conversation}
