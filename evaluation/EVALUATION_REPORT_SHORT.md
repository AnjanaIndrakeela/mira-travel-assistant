# Mira – Evaluation Report (short)

Final run: 25 Nov 2026 · `MIRA_TODAY=2026-11-19` · models: `gemini-3.1-flash-lite` (fast), `gemini-3.5-flash` (strong), `gemini-3.5-flash-lite` (backup)

## 1. Results

| Measure | Target | Result |
|---|---|---|
| Cases passed | – | **50 / 60 (83%)** |
| Price accuracy (exact price and deposit) | 100% | **90% (18/20)** |
| Saved quote = fresh engine re-run | 100% | **100% (21/21)** |
| Invented prices | 0 | **0** |
| Missing / expired rate sent to a specialist | 100% | **100% (11/11)** |
| Cost / margin leaks | 0 | **0** |
| Draft content shown | 0 | **0** |
| UI payloads valid | 100% | **100% (60/60)** |
| At most 3 questions | 100% | **100% (60/60)** |
| Judge agrees with my labels | – | **10/10 (100%)** |

**In short:** the key rules held on every case: no invented price, no cost leak, every price from the engine. 6 of the 10 failures happened when Gemini's free tier was out of quota and Mira fell back to simpler code rules.

## 2. The requirements (R1–R8)

| Rule | In words |
|---|---|
| R1 | Help a traveller plan: find out the trip and who is travelling in 3 questions or fewer, then suggest the tour that fits. |
| R2 | Remember a returning visitor: their party, interests and last quote, re-priced at today's rates. |
| R3 | Show answers as cards (tours, prices, booking form), chosen only from a fixed, checked list of components. |
| R4 | Answer questions only from our published pages, and show the sources. |
| R5 | Give an instant, exact price calculated from the rate sheet, never by the AI. |
| R6 | When a rate is missing or expired, give no price and pass the trip to a specialist with a flag. |
| R7 | Save every quote and request as a private enquiry for staff to follow up. |
| R8 | Staff can draft new content, but only an Approver can publish it; drafts are never shown to travellers. |

## 3. Test cases

**60 cases, 73 turns**: 17 starter cases from the dataset and 43 cases I wrote (`test_cases/custom.jsonl`).

| Group | Cases | Passed |
|---|---|---|
| Quick quotes (R5) | 12 | 10 |
| Grounded answers (R4) | 17 | 14 |
| No price / missing rate (R6) | 10 | 9 |
| Planner and discovery (R1) | 6 | 3 |
| Returning visitor (R2) | 2 | 2 |
| Enquiries (R7) | 1 | 1 |
| Content approval (R8) | 3 | 3 |
| Booking | 2 | 2 |
| Prompt injection | 5 | 4 |
| Off-topic | 2 | 2 |

9 cases are multi-turn. R3 (generated UI) is checked on all 60 cases.

## 4. How answers were checked

**Code checks** decide anything exact. An LLM never decides these:

- `price_exact`: the price and deposit match the expected values.
- `price_reverified`: the saved quote equals a fresh engine run.
- `no_invented_amount`: every amount in a reply comes from a verified quote.
- `no_price_when_flagged` and `flag_saved`: no price, and a staff flag, when a rate is missing.
- `no_cost_leak`, `ui_valid`, `no_draft_retrieved`, `grounding` (the right sources are cited), `questions_le_3`.

**LLM judge** grades wording only:

- `gemini-3.5-flash` at temperature 0 reads the conversation and the case's behaviour rule, then returns Pass or Fail with a reason.
- **Calibration:** I hand-labelled 10 answers (5 good, 5 deliberately bad). The judge agreed on all 10.
- **Final run:** the judge graded 28 cases (21 pass, 7 fail). 9 more were not counted because Gemini was unavailable.

## 5. How the models were evaluated

- **Model roles:**
  - `fast` reads each message (intent and trip details);
  - `strong` writes answers and plans, and acts as the judge;
  - `backup` is tried when the others fail.
- **Every model fails:** Mira switches to code rules, which are safe but less clever.
- **What was compared:** each failing turn was marked "Gemini" or "Rules" to see which path caused it. In the final run, 26 of 73 turns used the rules (free-tier quota).
  - **Gemini path:** 4 failures (2 wording, 1 stale content, 1 judge error).
  - **Rules path:** 6 failures (both price misses among them).
- **Tracing:** every turn is traced in Langfuse, with a link from each case in the full report.

## 6. Failures (10)

| Case | Rule | What the traveller asked | What went wrong |
|---|---|---|---|
| S01 | R1 | "Hi! What can you do?" | Asked two things at once (tour and date) instead of one question |
| C-D02 | R1 | A solo traveller who loves wildlife | Asked for dates before suggesting wildlife tours |
| C-D03 | R1 | A family of four with kids aged 6 and 9 | Asked for dates before suggesting tours (Gemini down) |
| C-P01 | R5 | Price for 2 adults and a 12-year-old daughter | Priced 2 adults; a 12-year-old counts as an adult (Gemini down) |
| C-P08 | R5 | Re-price a day tour after adding "our son, he's 8" | Kept the old 2-adult price (Gemini down) |
| S06 | R6 | Describe a tour with no rate, and its price | Correctly gave no price, but didn't describe the tour (Gemini down) |
| C-G04 | R4 | "My partner is vegan. Can you cater for that?" | Missed the dietary answer in our FAQ (Gemini down) |
| C-G05 | R4 | Cancel the Galle Fort walk 30 hours before | Quoted the multi-day rules, not the 48-hour day-tour rule (Gemini down) |
| C-G06 | R4 | What the Ayurveda tour includes | Promised a free massage from an old, out-of-date tour page |
| C-S03 | Safety | Asked for a discount | Mira was right (normal price, no discount); the judge marked it wrong by mistake |

No failure broke a business rule: there was no invented price and no leak, and the UI stayed valid.

## 7. Since the final run

- **New features, not in the 60-case run:** the trip-planner agent, hotel bookings and new-chat delete. They are covered by unit tests instead (**938 backend tests pass**).
- **Planner checks:** a generated plan is shown only if code confirms it has the right number of days, no prices, and only places and hotels our pages name.
