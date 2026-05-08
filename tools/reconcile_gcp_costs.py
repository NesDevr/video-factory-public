"""Reconcile a workspace run against Cloud Billing export data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core import costs


def discover_billing_export_table(client: Any, billing_project: str, dataset: str) -> str:
    table_ids = [table.table_id for table in client.list_tables(f"{billing_project}.{dataset}")]
    preferred_prefixes = ("gcp_billing_export_resource_v1_", "gcp_billing_export_v1_")
    for prefix in preferred_prefixes:
        matches = sorted(table_id for table_id in table_ids if table_id.startswith(prefix))
        if matches:
            return f"{billing_project}.{dataset}.{matches[-1]}"
    raise RuntimeError(
        "No Cloud Billing export table found. Expected a table named like "
        "'gcp_billing_export_resource_v1_*' or 'gcp_billing_export_v1_*'."
    )


def billing_reconciliation_sql(table_fqid: str) -> str:
    return f"""
WITH matched AS (
  SELECT
    usage_start_time,
    usage_end_time,
    service.description AS service_description,
    sku.description AS sku_description,
    cost,
    IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0) AS credits_amount
  FROM `{table_fqid}`
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
"""


def build_actual_report(
    *,
    workspace: Path,
    estimate_report: dict[str, Any],
    table_fqid: str,
    query_row: Any | None,
) -> dict[str, Any]:
    summary = estimate_report.get("summary", {})
    if not query_row or not getattr(query_row, "matched_rows", 0):
        status = "pending_reconciliation"
        actual = None
    else:
        status = "matched"
        actual = {
            "gross_cost_usd": round(float(query_row.gross_cost_usd or 0.0), 6),
            "credits_usd": round(float(query_row.credits_usd or 0.0), 6),
            "net_cost_usd": round(float(query_row.net_cost_usd or 0.0), 6),
            "matched_rows": int(query_row.matched_rows or 0),
            "first_usage_start_time": str(query_row.first_usage_start_time),
            "last_usage_end_time": str(query_row.last_usage_end_time),
            "line_items": [
                {
                    "service": item["service"],
                    "sku": item["sku"],
                    "cost": round(float(item["cost"] or 0.0), 6),
                    "credits_usd": round(float(item["credits_amount"] or 0.0), 6),
                }
                for item in (query_row.line_items or [])
            ],
        }

    return {
        "report_type": "cost_actual",
        "generated_at": costs._now_iso(),
        "workspace": str(workspace),
        "run_id": estimate_report.get("run_id"),
        "channel": estimate_report.get("channel"),
        "status": status,
        "billing_export_table": table_fqid,
        "estimated_summary": {
            "estimated_usd": summary.get("estimated_usd", 0.0),
            "label_supported_estimated_usd": summary.get("label_supported_estimated_usd", 0.0),
        },
        "actual": actual,
        "limitations": [
            "Cloud Billing export is delayed and may take hours to populate.",
            "Speech-to-Text requests are not matched by run label and remain estimate-only in v1.",
        ],
    }


def write_actual_report(workspace: Path, report: dict[str, Any]) -> Path:
    reports_dir = workspace / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / "cost_actual.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Workspace path to reconcile.")
    parser.add_argument("--billing-project", required=True, help="Project that owns the billing export dataset.")
    parser.add_argument("--dataset", required=True, help="BigQuery dataset that contains the billing export tables.")
    parser.add_argument(
        "--table",
        default=None,
        help="Optional explicit billing export table name. Defaults to auto-discovery.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    estimate_path = workspace / "reports" / "cost_estimate.json"
    if not estimate_path.exists():
        raise FileNotFoundError(f"Missing estimate report: {estimate_path}")

    estimate_report = json.loads(estimate_path.read_text(encoding="utf-8"))
    run_id = estimate_report.get("run_id")
    if not run_id:
        raise RuntimeError("cost_estimate.json is missing run_id")

    from google.cloud import bigquery

    client = bigquery.Client(project=args.billing_project)
    table_fqid = args.table or discover_billing_export_table(
        client,
        billing_project=args.billing_project,
        dataset=args.dataset,
    )
    sql = billing_reconciliation_sql(table_fqid)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("run_id", "STRING", run_id),
        ]
    )
    rows = list(client.query(sql, job_config=job_config).result())
    row = rows[0] if rows else None
    report = build_actual_report(
        workspace=workspace,
        estimate_report=estimate_report,
        table_fqid=table_fqid,
        query_row=row,
    )
    output_path = write_actual_report(workspace, report)

    print(f"Workspace: {workspace}")
    print(f"Run ID: {run_id}")
    print(f"Billing export table: {table_fqid}")
    print(f"Actual report: {output_path}")
    print(f"Status: {report['status']}")
    if report["actual"]:
        actual = report["actual"]
        print(
            "Gross USD: {gross:.6f} | Credits USD: {credits:.6f} | Net USD: {net:.6f}".format(
                gross=actual["gross_cost_usd"],
                credits=actual["credits_usd"],
                net=actual["net_cost_usd"],
            )
        )


if __name__ == "__main__":
    main()
