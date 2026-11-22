# Dataset notes

Notes from reading the supplied dataset (`ceylon-compass-dataset/`, 37 files) **before** writing the loaders. The dataset is used exactly as supplied: nothing in it is edited, and every fix below happens in loader code, in memory. The full machine-generated list of issues is in [data-issues.md](data-issues.md).

## Files

| Folder | Contents |
|---|---|
| `content/tours/` | 16 tour pages (T01–T16) |
| `content/destinations/` | 10 destination pages (D01–D10) |
| `content/policies/` | P01 booking and payment, P02 cancellation, P03 children and infants, P04 FAQ, P05 about us, P06 testimonials |
| `rates/` | `rate_sheet_2026-27.xlsx` (tabs READ ME, Settings, Seasons, Tours, Hotels, Transport) and `sample_quotes.md` (4 quotes) |
| `brand/` | `brand_pack.json` |
| `evals/` | `eval_seed.jsonl`: **17 cases** (S01–S17). The dataset README says 15; all 17 are used. |

Every content file has front matter with `id`, `type`, `title`, `status`, `last_updated`. Tours add `category`, `duration`, `start`, `destinations`, and sometimes `hotels` and `teaser_price`.

## Pricing rules (workbook READ ME, in my own words)

1. Buy costs are in LKR and we sell in USD, at the FX rate on Settings (300 LKR per USD), fixed until 31 Oct 2027.
2. Cost = guide per day × days + vehicle per day × days + entrance per person (whole tour) + meals per person per day × days + hotel rooms per night.
3. The vehicle depends on group size = adults + children aged 2–11 (Transport tab: Car 1–3, Van 4–8, Mini coach 9–20).
4. Rooms: two adults share a double; an odd adult takes a single; each child aged 2–11 gets an extra bed, every night.
5. Children aged 2–11 pay the child entrance fee and 50% of the adult meal cost. Infants under 2 are free (no seat, entrance, meals or bed).
6. The hotel rate is the row whose Valid from / Valid to covers that night. Night 1 = the start date.
7. Sell = cost ÷ (1 − margin). Margin is gross profit on the selling price: 30% for day tours, 25% for multi-day.
8. Round the booking total **up** to the next USD 5.
9. Deposit: day tours pay in full. Multi-day pays 25%, rounded up to a whole USD, with the balance due 30 days before the start. Tours starting within 30 days pay in full.
10. Maximum 20 travellers; bigger groups go to Sales.
11. If a rate isn't in the workbook, don't make one up: send it to Sales.

There is **no** separate single, child or accommodation "supplement". Those effects come only from rules 4 and 5.

## Workbook columns used for pricing

- **Settings:** FX rate, margin day / multi-day, multi-day deposit, full payment within (days), max group size, round-up step. The FX "valid until" date is only in the Notes column (`Fixed for quoting until 31 Oct 2027`).
- **Seasons:** Season, From, To (1 Nov 2026 – 31 Oct 2027).
- **Tours:** Tour ID, Tour, Type (`Day tour` / `Multi-day`), Days, Nights, Guide per day, Entrance adult, Entrance child 2–11, Meals per adult per day, Hotels by night (comma list, `–` for none), Notes.
- **Hotels:** the header is on **row 3**, not row 1. Columns: Hotel ID, Hotel, Season, Valid from, Valid to, Double, Single, Extra bed (child), Notes. Rates are per **room** per night.
- **Transport:** Vehicle, Min, Max, LKR per day.

## Traps found

| Where | What | How the loader handles it |
|---|---|---|
| Hotels H02 (rows 8, 10) | Double rate stored as text `LKR 28,000` | Parsed to 28000; logged |
| Hotels H08 row 33 | Valid-from stored as the text `15/12/2026` | Parsed as day-first; logged |
| Hotels H10 | Rates are in **USD** ("Cinnamon contract") | `currency = USD`; never divided by the FX rate |
| Hotels H04 | No single-room rate in any season | Stays empty (never 0): a solo traveller or odd adult on T12 cannot be priced |
| Hotels H07 | All rows end 31 Oct 2026, before the quoting year | No covering row: T11 cannot be priced |
| Hotels H03 row 56 | A second Peak row, 1 Jan–31 Mar 2027, overlapping row 13, note "Revised per supplier email?" | Logged as a conflict; never silently picks one |
| Tours | `T-13` while the content says `T13` | Normalised to `T13`; logged |
| Tours T15 | Note "New version – not launched yet"; the content is a draft | Never offered or priced |
| Tours T10, T16 | Published pages with no rate row | Described, never priced |
| T06 | The page says "1 night / 2 days"; the workbook says a 1-day day tour | Priced from the workbook |

| Where | What | How the loader handles it |
|---|---|---|
| `destinations/mirissa.md` | A hidden HTML comment addressed to the assistant, trying to change pricing | HTML comments are stripped on load; logged |
| `policies/testimonials.md` | Guest claims of discounts and upgrades, whales "in August", and a line addressed to the assistant asking it to favour one tour | Marked as guest **opinion**: never used as facts, prices or promises |
| P02 cancellation | "Replaces any cancellation terms shown on older pages" | P02 wins over T04's own cancellation section |
| P03 children | "Replaces any older family offers" | P03 wins over T07's "kids under 12 stay free" |
| T06, T07, T14, T16 | Last updated before 2025 | Marked stale |
| T14 | "Winter 2023/24 Early Bird Deal": an offer for a season that has ended | Marked as an expired offer; never bookable |
| Tour front matter | `teaser_price` strings ("From USD 40 per person") | Never shown; prices come only from the pricing engine |

## Sample quotes

| Quote | Tour, party, start | Sent | Check |
|---|---|---|---|
| Q-1041 | T01, 2 adults, 10 Jan 2027 | USD 315 / 315 | Matches the rules |
| Q-1042 | T09, 2 adults, 3 May 2027 | USD 2,125 / 532 | Matches |
| Q-1043 | T09, 2 adults + children 7 and 10, 12 Apr 2027 | USD 2,680 / 670 | **To investigate**: hotels are LKR 146,000, the same as for 2 adults, so the children's extra beds look missing |
| Q-1044 | T08, 2 adults, 1 Dec 2026 | USD 2,505 / 2,505 | Matches (starts within 30 days → full payment) |

## Brand pack

Orange `#F26B1D`, black `#111111`, five accents (teal, leaf, sun, sky, coral), Inter. Card radius 12 px, max width 320 px, one accent colour per card. Pill buttons (radius 999), input radius 8. Transitions under 200 ms, with no parallax.

Tone of voice: short sentences, warm but no exclamation marks in prices or policies, never promise what the content or rates don't support, "we" for the company and "I" for Mira. Don't use photos or brand names we have no rights to.
