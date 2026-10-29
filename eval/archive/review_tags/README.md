# Archive: review tags (M3, 2026-10-28 → 2026-10-29)

Not used any more. The review tags were dropped on 2026-10-29: Haiku now returns only the
translation (§0 of `docs/v3-problem-statement.md`, "Tags dropped for now"). Kept as the record
of why.

- `results/` — gold runs 1–3 (prompt 0.1.0 / 0.2.0 / 0.3.0): none passed the 90% mark.

The tag gold set (`review_tags_v3.yaml`) and the scorer (`review_gold.py` + its tests) are in
git, commit `8d46343`. The texts and meanings of that gold set live on in
`eval/gold/review_translate.yaml`.

To bring tags back: restore the code from that commit, write a new tag list and prompt
version, and score against a gold set first (§0 says how to update the rows).
