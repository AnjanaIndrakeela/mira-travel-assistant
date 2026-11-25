# Mira evaluation report

Run 2026-11-24 00:38 UTC · `MIRA_TODAY=2026-11-19` · models `gemini-3.1-flash-lite` (fast), `gemini-3.5-flash` (strong), `gemini-3.5-flash-lite` (backup) · commit `491c5b6`

**36/43 cases passed** (84%) · 52 turns · 7 multi-turn cases · average 5.6 s per turn

- **Dataset integrity:** OK. Dataset integrity OK (37 files unchanged)
- **Gemini fallbacks:** 1 of 52 turns were read by the code rules because every Gemini model failed (quota, overload or timeout). Those turns still count.
- **Behaviour cases (20):** checked by code only in this run (no invented amounts, valid UI, no leaks, grounding where the case lists sources). The LLM judge for their wording comes in Phase 15.

## Targets vs actual

| Measure | Target | Actual | |
|---|---|---|---|
| Price accuracy (exact price and deposit) | 100% | 83% (10/12) | ❌ |
| Quotes equal to the engine re-run | 100% | 100% (12/12) | ✅ |
| Invented amounts (cases with one) | 0 | 0 | ✅ |
| Missing / expired rate handled (no price + flag saved) | 100% | 70% (7/10) | ❌ |
| Cost / margin / GP% leaks | 0 | 0 | ✅ |
| Draft or unpublished docs retrieved | 0 | 0 | ✅ |
| UI payloads valid | 100% | 100% (43/43) | ✅ |
| At most 3 questions | 100% | 100% (43/43) | ✅ |

## Pass rate per requirement

| Requirement | Cases | Passed | Rate |
|---|---|---|---|
| R1 | 2 | 2 | 100% (2/2) |
| R4 | 17 | 15 | 88% (15/17) |
| R5 | 12 | 10 | 83% (10/12) |
| R6 | 10 | 7 | 70% (7/10) |
| Safety | 1 | 1 | 100% (1/1) |
| Off-topic | 1 | 1 | 100% (1/1) |

## Pass rate per check

| Check | Applies to | Passed | Rate |
|---|---|---|---|
| `no_error` | 43 | 43 | 100% (43/43) |
| `no_invented_amount` | 43 | 43 | 100% (43/43) |
| `ui_valid` | 43 | 43 | 100% (43/43) |
| `no_cost_leak` | 43 | 43 | 100% (43/43) |
| `questions_le_3` | 43 | 43 | 100% (43/43) |
| `price_exact` | 12 | 10 | 83% (10/12) |
| `price_reverified` | 12 | 12 | 100% (12/12) |
| `no_price_when_flagged` | 10 | 9 | 90% (9/10) |
| `flag_saved` | 10 | 7 | 70% (7/10) |
| `no_draft_retrieved` | 13 | 13 | 100% (13/13) |
| `grounding` | 11 | 9 | 82% (9/11) |
| `custom_enquiry` | 1 | 1 | 100% (1/1) |

## Failing cases (7)

### S11 · R6 · flag_no_price

- ❌ **flag_saved**: saved no flagged enquiry

1. **Traveller:** How much is an airport transfer from CMB to Kandy for 2 people?
   **Mira** (match_tours, 12.4 s, [trace](https://us.cloud.langfuse.com/project/cmwrtjux0008aad0hwegig0nm/traces/79798738ab455e4f221794bf5457a9ba)): I can help you plan your trip to Kandy. Here are a few tours that might suit you: Kandy City Tour (1 day, visits Kandy), Highlights of Sri Lanka (7 nights / 8 days, visits Kandy), and Cultural Triangle Sri Lanka Package (6 nights / 7 days, visits Kandy). Could you tell me your start date?

### S15 · R5 · quote

- ❌ **price_exact**: expected [('T05', 275, 275)], got no priced quote

1. **Traveller:** Whale watching in Mirissa on 15 March 2027 for 2 adults and our 1-year-old baby. Price?
   **Mira** (match_tours, 6.8 s, [trace](https://us.cloud.langfuse.com/project/cmwrtjux0008aad0hwegig0nm/traces/25af5ddb2bbcd6199c5a82b4439286f7)): A travel specialist will confirm the price for these dates. Here are the tours that fit your interest in whale watching: Whale and Dolphin Watching Tour in Mirissa (1 day, visits Mirissa) for a quick day trip, Instafamous Sri Lanka (10 nights / 11 days, visits Mirissa) for an extended photography adventure, and Sri Lanka Beach Stay – Mirissa (6 nights / 7 days, visits Mirissa) for a relaxing coastal holiday. I can price any of these once you share which tour you would like.

### C-P02 · R5 · quote

_5 adults: Van, 2 doubles + 1 single_  
- ❌ **price_exact**: expected [('T09', 4475, 1119)], got no priced quote

1. **Traveller:** Five adults, the Cultural Triangle Sri Lanka Package starting 3 May 2027. How much is it?
   **Mira** (ask, 4.2 s, [trace](https://us.cloud.langfuse.com/project/cmwrtjux0008aad0hwegig0nm/traces/f8c7aa9ba87a6ba44659d46071176e12)): A travel specialist will confirm the price for these dates and get back to you. Could you tell me the age of each child?

### C-R01 · R6 · flag_no_price

_expired offer T14 -> stale_tour_  
Expected: Does not show any price or amount; says a travel specialist will confirm; raises a staff flag.  
- ❌ **flag_saved**: wanted flag 'stale_tour', saved [['custom_request', 'no_price']]

1. **Traveller:** Can I book the Popular Stays Winter 2023/24 Early Bird Deal for 2 adults from 3 May 2027? How much?
   **Mira** (match_tours, 14.2 s, [trace](https://us.cloud.langfuse.com/project/cmwrtjux0008aad0hwegig0nm/traces/6e9a704bcff17ddb4ab9009a53c26e5e)): We do not have a Popular Stays Winter 2023/24 Early Bird Deal in our catalogue, but I can pass your request to a travel specialist. For your dates, we offer these tours: Wildlife Photography Tour for a focus on Udawalawe and Yala, Sigiriya and Minneriya Day Tour from Kandy for a quick visit to Minneriya, or Highlights of Sri Lanka for a broader experience including Minneriya. A travel specialist will confirm the price for these dates once you let me know which tour you prefer.

### C-R05 · R6 · flag_no_price

_older 5-night page T16 has no rate row (not to be confused with T09)_  
Expected: Does not show any price or amount; says a travel specialist will confirm; raises a staff flag.  
- ❌ **no_price_when_flagged**: priced on turn(s) [1]
- ❌ **flag_saved**: wanted flag 'no_rate_row', saved no flagged enquiry

1. **Traveller:** How much is the 5-night Cultural Triangle Tour for 2 adults from 3 May 2027?
   **Mira** (price, 1.9 s, [trace](https://us.cloud.langfuse.com/project/cmwrtjux0008aad0hwegig0nm/traces/11b3c83ddfc7cd2bd3ee9c34fa893ab2)): Here is your price for the Cultural Triangle Sri Lanka Package, 3 May 2027 to 9 May 2027, for 2 adults: USD 2,125 in total. To book, the deposit is USD 532, and the balance of USD 1,593 is due by 3 April 2027. Would you like to book, or change the dates or travellers?

### C-G01 · R4 · behaviour

_multi-day cancellation terms come from P02_  
Expected: Says 8 to 29 days before the start gives a 50% refund, citing the cancellation policy.  
- ❌ **grounding**: cited none of ['P02'] (cited nothing)

1. **Traveller:** If we cancel the Highlights of Sri Lanka tour 20 days before it starts, what refund do we get?
   **Mira** (retrieve, 18.2 s, [trace](https://us.cloud.langfuse.com/project/cmwrtjux0008aad0hwegig0nm/traces/601168d7befea234cefe9c1b71b610c4)): Here is what our Cancellation policy page says: Cancellation policy — Multi-day tours and stays - 30 days or more before the start: full refund minus a [amount: a travel specialist can confirm] admin fee. - 8 to 29 days before the start: 50% refund. - 7 days or less: no refund. [1]

### C-G09 · R4 · behaviour

_infants: free, share parents' seat and bed (P03)_  
Expected: Says infants under 2 travel free and share their parents' seat and bed, citing the children and infants policy.  
- ❌ **grounding**: cited none of ['P03'] (cited nothing)

1. **Traveller:** We're bringing our 1-year-old. Does she need her own seat or bed, and do we pay for her?
   **Mira** (retrieve, 2.0 s, [trace](https://us.cloud.langfuse.com/project/cmwrtjux0008aad0hwegig0nm/traces/adfe00b9019c7e328fc9a711f2b9fa48)): Here is what our Booking and payment page says: Booking and payment — Payment - **Day and city tours:** pay the full amount when you book. - **Multi-day tours and stays:** pay a 25% deposit to confirm. The balance is due 30 days before the start. If you book within 30 days of the start date, the full amount is due when you book. - We accept Visa, Mastercard and American Express through a secure payment link. We do not accept cryptocurrency. [1]

## All cases

| Case | Req | Type | Turns | Result | Time | Failed checks |
|---|---|---|---|---|---|---|
| S01 | R1 | behaviour | 1 | ✅ | 2.4 s |  |
| S02 | R5 | quote | 1 | ✅ | 2.1 s |  |
| S03 | R5 | quote | 2 | ✅ | 22.8 s |  |
| S04 | R6 | flag_no_price | 1 | ✅ | 10.5 s |  |
| S05 | R6 | flag_no_price | 1 | ✅ | 18.0 s |  |
| S06 | R6 | flag_no_price | 1 | ✅ | 1.6 s |  |
| S07 | R4 | behaviour | 1 | ✅ | 20.5 s |  |
| S08 | R4 | behaviour | 1 | ✅ | 3.6 s |  |
| S09 | R4 | behaviour | 1 | ✅ | 2.2 s |  |
| S10 | R4 | behaviour | 1 | ✅ | 3.4 s |  |
| S11 | R6 | flag_no_price | 1 | ❌ | 12.4 s | flag_saved |
| S12 | Safety | behaviour | 1 | ✅ | 0.0 s |  |
| S13 | R5 | quote_sequence | 3 | ✅ | 15.3 s |  |
| S14 | Off-topic | behaviour | 1 | ✅ | 1.6 s |  |
| S15 | R5 | quote | 1 | ❌ | 6.8 s | price_exact |
| S16 | R4 | behaviour | 1 | ✅ | 16.7 s |  |
| S17 | R4 | behaviour | 1 | ✅ | 3.9 s |  |
| C-P01 | R5 | quote | 2 | ✅ | 3.6 s |  |
| C-P02 | R5 | quote | 1 | ❌ | 4.2 s | price_exact |
| C-P03 | R5 | quote | 1 | ✅ | 1.5 s |  |
| C-P04 | R5 | quote | 1 | ✅ | 1.2 s |  |
| C-P05 | R5 | quote | 1 | ✅ | 1.4 s |  |
| C-P06 | R5 | quote | 1 | ✅ | 1.1 s |  |
| C-P07 | R5 | quote_sequence | 3 | ✅ | 7.8 s |  |
| C-P08 | R5 | quote_sequence | 2 | ✅ | 4.0 s |  |
| C-R01 | R6 | flag_no_price | 1 | ❌ | 14.2 s | flag_saved |
| C-R02 | R6 | flag_no_price | 1 | ✅ | 1.7 s |  |
| C-R03 | R6 | flag_no_price | 1 | ✅ | 2.8 s |  |
| C-R04 | R6 | flag_no_price | 1 | ✅ | 2.5 s |  |
| C-R05 | R6 | flag_no_price | 1 | ❌ | 1.9 s | no_price_when_flagged, flag_saved |
| C-R06 | R6 | flag_no_price | 1 | ✅ | 7.3 s |  |
| C-G01 | R4 | behaviour | 1 | ❌ | 18.2 s | grounding |
| C-G02 | R4 | behaviour | 1 | ✅ | 14.0 s |  |
| C-G03 | R4 | behaviour | 1 | ✅ | 2.3 s |  |
| C-G04 | R4 | behaviour | 1 | ✅ | 3.0 s |  |
| C-G05 | R4 | behaviour | 1 | ✅ | 2.6 s |  |
| C-G06 | R4 | behaviour | 1 | ✅ | 3.3 s |  |
| C-G07 | R4 | behaviour | 1 | ✅ | 1.1 s |  |
| C-G08 | R4 | behaviour | 1 | ✅ | 2.7 s |  |
| C-G09 | R4 | behaviour | 1 | ❌ | 2.0 s | grounding |
| C-G10 | R4 | behaviour | 1 | ✅ | 7.5 s |  |
| C-M01 | R1 | custom_enquiry | 2 | ✅ | 16.6 s |  |
| C-M02 | R4 | behaviour | 2 | ✅ | 16.8 s |  |

Generated by `python -m evaluation.runner`. Quotes and enquiries from this run are saved under the fixed eval visitor, so they show in the staff console like real chats.
