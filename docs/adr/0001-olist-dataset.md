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

A web search (2026-10-11) found no candidate meeting all criteria better.

## Consequences

- Reviews are in **Portuguese**; the manager works in English. How to handle this is a separate decision.
- Data covers **2016–2018**: relative dates ("last quarter") must resolve against the data's range, not today.
- Company names in review text were anonymised as Game of Thrones house names: real mess to handle.
- To verify during profiling: license (believed CC BY-NC-SA 4.0, so raw data is not committed; download script + attribution instead) and how many reviews have comment text.
- Possible later add-on: Olist's separate Marketing Funnel dataset (unverified) links to sellers.

## Questions that drove this

- What must the data have for the problem statement to be real (both sources, linked)?
- Is it real or synthetic? Would a reviewer see it as a tutorial dataset?
- Can one question need both sources?
- Does the license allow a public repo?
