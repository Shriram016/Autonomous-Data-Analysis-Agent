# Dataset: Olist Brazilian E-Commerce

We use the Olist Brazilian E-Commerce public dataset (~100k orders, 2016–2018, 9 related tables, customer reviews from a post-delivery survey). It is the only candidate that passes all four must-have criteria: real company data, several related tables, real mess, and customer text linked to the records. Because reviews are tied to orders, one question can naturally need both sources ("do late deliveries cause bad reviews, and what do those customers say?").

## Considered Options

| Dataset | Rejected because |
|---|---|
| Inside Airbnb | Scraped public listings, not a company's internal records; fewer tables |
| Yelp Open Dataset | Platform data, not one company; millions of reviews; restrictive terms; no natural actions |
| Instacart / H&M | No customer text |
| Northwind / TPC-H / SQL-practice sets | Fictional, clean, no text |
| Synthetic e-commerce sets (Kaggle, Hugging Face) | Generated data, not real |
| JD.com reviews | Review text without a linked order schema |

A web search (2026-10-11) found no candidate meeting all criteria better. Re-checked 2026-10-18 for a newer Olist release or a recent equivalent: none; recent open sets are synthetic (no real mess) or lack orders / review text. Olist kept: real messiness matters more than recent dates.

## Consequences

- Reviews are in **Portuguese**; the manager works in English. How to handle this is a separate decision.
- Data covers **2016–2018**: relative dates ("last quarter") must resolve against the data's range, not today; the exact rule is decided at implementation (Level 2).
- Company names in review text were anonymised as Game of Thrones house names: real mess to handle.
- License **confirmed CC BY-NC-SA 4.0** (Kaggle page, 2026-10-18; "expected update frequency: Never"): raw data is not committed; manual download + `prepare_olist` script + attribution in [docs/data-source.md](../data-source.md). Review-text share is checked in profiling (M0.5).
- Possible later add-on: Olist's separate Marketing Funnel dataset (unverified) links to sellers.

## Questions that drove this

- What must the data have for the problem statement to be real (both sources, linked)?
- Is it real or synthetic? Would a reviewer see it as a tutorial dataset?
- Can one question need both sources?
- Does the license allow a public repo?
