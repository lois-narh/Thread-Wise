-- name: All orders
-- note: Every cleaned order, newest first. Status is worked out from the dates.
SELECT o.order_id AS "Order", o.order_date AS "Ordered", c.name AS "Customer", t.name AS "Tailor",
       o.garment_type AS "Garment", o.occasion AS "Occasion",
       o.price_ghs AS "Price (GHS)", o.deposit_ghs AS "Deposit (GHS)",
       o.promised_date AS "Promised", o.delivered_date AS "Delivered",
       CASE WHEN o.delivered_date IS NOT NULL AND o.is_late = 1 THEN 'Delivered late'
            WHEN o.delivered_date IS NOT NULL THEN 'Delivered on time'
            WHEN o.promised_date < (SELECT MAX(order_date) FROM orders_clean) THEN 'Pending - overdue'
            ELSE 'Pending' END AS "Status"
FROM orders_clean o
JOIN customers c ON c.customer_id = o.customer_id
JOIN tailors t ON t.tailor_id = o.tailor_id
ORDER BY o.order_date DESC, o.order_id DESC;