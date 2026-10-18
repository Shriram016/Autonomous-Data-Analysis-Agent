# Data source: Olist Brazilian E-Commerce

**Dataset:** [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle, publisher `olistbr`)
**Licence:** [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — confirmed on the Kaggle page, 2026-10-18
**Update frequency:** "Never" (per the Kaggle page) — a fixed snapshot, ~Sep 2016 to Oct 2018

## Attribution

> Brazilian E-Commerce Public Dataset by Olist, provided by Olist (www.olist.com) on Kaggle,
> licensed under CC BY-NC-SA 4.0. Thanks to Olist for releasing this dataset.

## What the licence means for this project

| Term | Meaning | How ADAA complies |
|---|---|---|
| **BY** (attribution) | Credit the source | Attribution above; README links here |
| **NC** (non-commercial) | No commercial use | Portfolio / learning project only |
| **SA** (share-alike) | Adapted data must carry the same licence | Derived data (translations, topic tags, embeddings) is not redistributed; if it ever is, it carries CC BY-NC-SA 4.0 |

**Raw data is never committed.** It is downloaded by hand from Kaggle and prepared locally.

## How to get it

1. Download the ZIP from the Kaggle page (free login) into `data/raw/` (any `*.zip` name).
2. From `backend/`: `uv run python -m adaa.ingestion.prepare_olist`
   → extracts the 9 CSVs to `data/raw/olist/`, checks headers, writes `manifest.json`
   (rows, bytes, SHA-256 per file).
3. Verify: `uv run python dev_checks/check_data_files.py`

## Expected files (as prepared 2026-10-18)

| File | Rows |
|---|---:|
| olist_customers_dataset.csv | 99,441 |
| olist_geolocation_dataset.csv | 1,000,163 |
| olist_order_items_dataset.csv | 112,650 |
| olist_order_payments_dataset.csv | 103,886 |
| olist_order_reviews_dataset.csv | 99,224 |
| olist_orders_dataset.csv | 99,441 |
| olist_products_dataset.csv | 32,951 |
| olist_sellers_dataset.csv | 3,095 |
| product_category_name_translation.csv | 71 |

## Notes from the publisher worth remembering

- Real commercial data, anonymised; companies and partners named in review text were replaced
  with Game of Thrones great-house names.
- An order can have several items, each fulfilled by a different seller.
- The review survey is emailed after delivery, or when the estimated delivery date passes.
- A separate Marketing Funnel dataset by Olist can be joined to sellers (possible later add-on).
