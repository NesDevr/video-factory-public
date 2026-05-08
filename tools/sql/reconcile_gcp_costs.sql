WITH matched AS (
  SELECT
    usage_start_time,
    usage_end_time,
    service.description AS service_description,
    sku.description AS sku_description,
    cost,
    IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0) AS credits_amount
  FROM `{{TABLE_FQID}}`
  WHERE EXISTS (
    SELECT 1
    FROM UNNEST(labels) label
    WHERE label.key = 'vf_run' AND label.value = @run_id
  )
)
SELECT
  COUNT(*) AS matched_rows,
  MIN(usage_start_time) AS first_usage_start_time,
  MAX(usage_end_time) AS last_usage_end_time,
  SUM(cost) AS gross_cost_usd,
  SUM(credits_amount) AS credits_usd,
  SUM(cost) + SUM(credits_amount) AS net_cost_usd,
  ARRAY_AGG(
    STRUCT(
      service_description AS service,
      sku_description AS sku,
      cost,
      credits_amount
    )
    ORDER BY cost DESC
    LIMIT 25
  ) AS line_items
FROM matched
