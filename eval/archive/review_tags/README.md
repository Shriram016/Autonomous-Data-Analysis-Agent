# Archive: review tags (M3, 2026-10-28 → 2026-10-29)

Not used any more. The review tags were dropped on 2026-10-29: Haiku now returns only the
translation (§0 of `docs/v3-problem-statement.md`, "Tags dropped for now"). Kept as the record
of why.

- `gold/` — the 100-review gold set, tag list v3 (`.yaml` = source, `.md` = readable view).
- `results/` — gold runs 1–3 (prompt 0.1.0 / 0.2.0 / 0.3.0): none passed the 90% mark.
- `code/` — the scorer (`review_gold.py`) and its tests. It no longer runs: it imports the
  removed `adaa.ingestion.review_tags` module.

To bring tags back: restore the code from here, write a new tag list and prompt version, and
score against a gold set first (§0 says how to update the rows).
