# Olist data profile

## Findings and impact

*Written 2026-10-19 after reading the numbers below. Each impact line is input for M0.6 (semantic
layer) and for the eval traps.*

### Design estimates: confirmed or corrected

| Estimate in the design | Real value | Result |
|---|---|---|
| ~100k orders | 99,441 | Confirmed |
| ~40% of reviews have text | 41.3% (40,977 reviews) | Confirmed: the translate / tag / embed cost estimate stands |
| Data covers 2016–2018 | 2016-09-04 to 2018-10-17 | Confirmed, but only **2017-01 to 2018-08** is usable (see F1) |

### Findings

| # | Finding | Impact |
|---|---|---|
| F1 | **Usable window is 2017-01 to 2018-08** (20 months, 800–7,544 orders per month). The ends are thin: 2016-09 (4), 2016-10 (324), 2016-12 (1), 2018-09 (16), 2018-10 (4). **2016-11 has no orders.** | Trend answers warn on thin months. "Latest full month" = 2018-08. Input for the deferred "what is today" decision. Eval trap: "sales in Nov 2016" = 0, not an error. |
| F2 | **Revenue depends on the definition.** Item price only = 13.59M; price + freight = 15.84M; payment value = 16.01M (18% above price only). Per order, price + freight equals payment in 99.7% of orders. The 165,319 gap between price + freight and payment comes 98% from **775 orders with a payment but no items** (603 unavailable, 164 canceled), and only 2% (2,871) from 303 orders with interest or vouchers. | M0.6 defines revenue = item price (D1); freight and total paid are separate metrics. The delivered-only filter removes the incomplete orders. Strongest eval trap: the same question gives 13.6M or 16.0M. |
| F3 | **97.0% of orders are delivered.** 625 canceled, 609 unavailable, 1,107 shipped. 775 orders have no items. | Revenue and delivery metrics need an explicit status filter (default: delivered). |
| F4 | **One person can have several `customer_id` values.** 99,441 `customer_id` vs 96,096 people (`customer_unique_id`). Only 3.1% of people ordered more than once. | Customer counts use `customer_unique_id`. Eval trap: `customer_id` overstates people by 3.5% and hides repeat buyers. |
| F5 | **`review_id` is not unique.** 789 IDs repeat across 1,603 rows. 547 orders have 2+ reviews; 768 orders have none. | A review is a (`review_id`, `order_id`) row. "Average score per order" needs a rule for orders with 2+ reviews. |
| F6 | **Unhappy customers write more.** 76.5% of 1-star reviews have a comment, but only 35.9% of 5-star reviews. Comments are short (median 53 characters). | Review-text answers must say "of reviews with a comment" and must not treat text share as overall satisfaction. Short text keeps translation cheap. |
| F7 | **6.8% of delivered orders were late** (delivery date after the estimated date, at day level). When late, the average is 10.6 days late. Average delivery takes 12.5 days. 8 delivered orders have no delivery date; 6 undelivered orders have one. | Late-delivery rate = delivered orders with a delivery date, compared by day. ~6.5k late orders give enough data for hybrid questions. |
| F8 | **Missing links:** 610 products have no category; 2 categories have no English name (`pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`); 157 customer zip prefixes are not in `geolocation`; 1 order has no payment. | Category breakdowns show an "unknown" group; untranslated categories fall back to the Portuguese name. Maps are partial. |
| F9 | **Strange but real values:** 9 payments of 0 (vouchers), 3 with type `not_defined`, 2 with 0 instalments; 4,124 items where freight > price (cheap items); 42 geolocation points outside Brazil. Prices from 0.85 to 6,735 (median 74.99). | Keep the rows (faithful load). Exclude points outside Brazil from maps. No price outlier rule needed.

**Status:** the profile answers all 10 areas. F2, F3, F4, F5 and F7 are the main inputs for M0.6.

<!-- GENERATED BELOW: do not edit by hand; rerun profile_olist -->

*Generated 2026-10-19 from schema `business`.*

## 1. Basic shape

| table | rows |
|---|---|
| customers | 99,441 |
| geolocation | 1,000,163 |
| orders | 99,441 |
| order_items | 112,650 |
| payments | 103,886 |
| reviews | 99,224 |
| products | 32,951 |
| sellers | 3,095 |
| category_translation | 71 |

**customers**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| customer_id | text | 0.00 | 99,441 |
| customer_unique_id | text | 0.00 | 96,096 |
| customer_zip_code_prefix | text | 0.00 | 14,994 |
| customer_city | text | 0.00 | 4,119 |
| customer_state | text | 0.00 | 27 |

**geolocation**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| geolocation_zip_code_prefix | text | 0.00 | 19,015 |
| geolocation_lat | double precision | 0.00 | 717,372 |
| geolocation_lng | double precision | 0.00 | 717,615 |
| geolocation_city | text | 0.00 | 8,011 |
| geolocation_state | text | 0.00 | 27 |

**orders**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| order_id | text | 0.00 | 99,441 |
| customer_id | text | 0.00 | 99,441 |
| order_status | text | 0.00 | 8 |
| order_purchase_timestamp | timestamp without time zone | 0.00 | 98,875 |
| order_approved_at | timestamp without time zone | 0.20 | 90,733 |
| order_delivered_carrier_date | timestamp without time zone | 1.80 | 81,018 |
| order_delivered_customer_date | timestamp without time zone | 3.00 | 95,664 |
| order_estimated_delivery_date | timestamp without time zone | 0.00 | 459 |

**order_items**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| order_id | text | 0.00 | 98,666 |
| order_item_id | integer | 0.00 | 21 |
| product_id | text | 0.00 | 32,951 |
| seller_id | text | 0.00 | 3,095 |
| shipping_limit_date | timestamp without time zone | 0.00 | 93,318 |
| price | numeric | 0.00 | 5,968 |
| freight_value | numeric | 0.00 | 6,999 |

**payments**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| order_id | text | 0.00 | 99,440 |
| payment_sequential | integer | 0.00 | 29 |
| payment_type | text | 0.00 | 5 |
| payment_installments | integer | 0.00 | 24 |
| payment_value | numeric | 0.00 | 29,077 |

**reviews**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| review_id | text | 0.00 | 98,410 |
| order_id | text | 0.00 | 98,673 |
| review_score | integer | 0.00 | 5 |
| review_comment_title | text | 88.30 | 4,527 |
| review_comment_message | text | 58.70 | 36,159 |
| review_creation_date | timestamp without time zone | 0.00 | 636 |
| review_answer_timestamp | timestamp without time zone | 0.00 | 98,248 |

**products**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| product_id | text | 0.00 | 32,951 |
| product_category_name | text | 1.90 | 73 |
| product_name_lenght | integer | 1.90 | 66 |
| product_description_lenght | integer | 1.90 | 2,960 |
| product_photos_qty | integer | 1.90 | 19 |
| product_weight_g | integer | 0.00 | 2,204 |
| product_length_cm | integer | 0.00 | 99 |
| product_height_cm | integer | 0.00 | 102 |
| product_width_cm | integer | 0.00 | 95 |

**sellers**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| seller_id | text | 0.00 | 3,095 |
| seller_zip_code_prefix | text | 0.00 | 2,246 |
| seller_city | text | 0.00 | 611 |
| seller_state | text | 0.00 | 23 |

**category_translation**

| column | type | null_pct | distinct_values |
|---|---|---|---|
| product_category_name | text | 0.00 | 71 |
| product_category_name_english | text | 0.00 | 71 |

## 2. Time range

| first_order | last_order |
|---|---|
| 2016-09-04 21:15:19 | 2018-10-17 17:30:18 |

Orders per month (thin = fewer than 500):

| month | orders | thin |
|---|---|---|
| 2016-09 | 4 | yes |
| 2016-10 | 324 | yes |
| 2016-12 | 1 | yes |
| 2017-01 | 800 | no |
| 2017-02 | 1,780 | no |
| 2017-03 | 2,682 | no |
| 2017-04 | 2,404 | no |
| 2017-05 | 3,700 | no |
| 2017-06 | 3,245 | no |
| 2017-07 | 4,026 | no |
| 2017-08 | 4,331 | no |
| 2017-09 | 4,285 | no |
| 2017-10 | 4,631 | no |
| 2017-11 | 7,544 | no |
| 2017-12 | 5,673 | no |
| 2018-01 | 7,269 | no |
| 2018-02 | 6,728 | no |
| 2018-03 | 7,211 | no |
| 2018-04 | 6,939 | no |
| 2018-05 | 6,873 | no |
| 2018-06 | 6,167 | no |
| 2018-07 | 6,292 | no |
| 2018-08 | 6,512 | no |
| 2018-09 | 16 | yes |
| 2018-10 | 4 | yes |

## 3. Duplicates

| review_ids_used_more_than_once | rows_involved |
|---|---|
| 789 | 1,603 |

| orders_with_2plus_reviews | orders_with_no_review |
|---|---|
| 547 | 768 |

## 4. Customers

| customer_ids | real_people |
|---|---|
| 99,441 | 96,096 |

| people_with_2plus_orders | pct_repeat |
|---|---|
| 2,997 | 3.10 |

## 5. Missing links

| check | count |
|---|---|
| products with no category | 610 |
| categories with no English name | 2 |
| order items whose product is missing | 0 |
| orders with no items | 775 |
| orders with no payment | 1 |
| reviews whose order is missing | 0 |
| customer zip prefixes not in geolocation | 157 |

| untranslated_category |
|---|
| pc_gamer |
| portateis_cozinha_e_preparadores_de_alimentos |

## 6. Revenue trap

| orders_with_both | equal | different | pct_different | max_difference |
|---|---|---|---|---|
| 98,665 | 98,362 | 303 | 0.30 | 182.81 |

| sum_item_price | sum_freight | sum_payment_value |
|---|---|---|
| 13,591,643.70 | 2,251,909.54 | 16,008,872.12 |

## 7. Order status

| order_status | orders | pct |
|---|---|---|
| delivered | 96,478 | 97.02 |
| shipped | 1,107 | 1.11 |
| canceled | 625 | 0.63 |
| unavailable | 609 | 0.61 |
| invoiced | 314 | 0.32 |
| processing | 301 | 0.30 |
| created | 5 | 0.01 |
| approved | 2 | 0.00 |

| delivered_but_no_delivery_date | not_delivered_but_has_date |
|---|---|
| 8 | 6 |

## 8. Delivery

| delivered_with_date | late | pct_late | avg_days_late_when_late | avg_days_to_deliver |
|---|---|---|---|---|
| 96,470 | 6,534 | 6.80 | 10.60 | 12.50 |

| bucket | orders |
|---|---|
| on time or early | 89,936 |
| 1-7 days late | 3,672 |
| 8-30 days late | 2,517 |
| over 30 days late | 345 |

## 9. Reviews

| reviews | pct_with_title | pct_with_comment | avg_comment_chars | median_comment_chars |
|---|---|---|---|---|
| 99,224 | 11.70 | 41.30 | 69.00 | 53.00 |

| review_score | reviews | pct_of_reviews | pct_with_comment |
|---|---|---|---|
| 1 | 11,424 | 11.50 | 76.50 |
| 2 | 3,151 | 3.20 | 68.10 |
| 3 | 8,179 | 8.20 | 43.50 |
| 4 | 19,142 | 19.30 | 31.20 |
| 5 | 57,328 | 57.80 | 35.90 |

## 10. Strange values

| check | count |
|---|---|
| payments with value 0 | 9 |
| payments with 0 instalments | 2 |
| payments with type not_defined | 3 |
| items where freight > price | 4,124 |
| products with no weight | 2 |
| geolocation points outside Brazil | 42 |

| min_price | median_price | max_price | max_freight |
|---|---|---|---|
| 0.85 | 74.99 | 6,735.00 | 409.68 |
