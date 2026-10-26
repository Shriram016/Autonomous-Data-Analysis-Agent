version: 0.1.0

## Business rules

- Revenue (sales) = the sum of `order_items.price`. Freight is not revenue.
- Count only delivered orders (`orders.order_status = 'delivered'`) unless the question names
  an order status. A cancellation rate is a share of all orders, in every status.
- A customer is one person: count `customers.customer_unique_id`, not `customer_id`.
- Count orders as distinct `order_id`.
- An order is late when `order_delivered_customer_date::date >
  order_estimated_delivery_date::date` (delivered orders with a delivery date only).
- Delivery days = `order_delivered_customer_date::date - order_purchase_timestamp::date`.
- A period means the order purchase date (`orders.order_purchase_timestamp`).
- Review metrics use every review row; no status filter.
