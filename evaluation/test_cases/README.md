# Eval cases

- `eval_seed.jsonl` (the 17 starters) is read from the dataset and never copied or changed.
- `custom.jsonl` holds our own cases, in the same format as the starters, plus:
  - `requirement`: the brief requirement it checks (R1–R8),
  - `note`: why the case exists,
  - `pricing_input` (pricing and rate cases): the structured booking the conversation describes,
    so the expected numbers can be re-checked against `calculate_quote()` without an LLM
    (`backend/tests/unit/test_eval_cases.py`). For `quote_sequence` it is a list, one per quote.
