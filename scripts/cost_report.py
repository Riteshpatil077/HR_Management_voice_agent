#!/usr/bin/env python
"""
LLM Cost Reporter Script.

Aggregates cost data from the PostgreSQL `call_analytics` table over a specified period.
Used by the weekly GitHub Action to post cost summaries to Slack and enforce budgets.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import create_engine, text

def generate_report(db_url: str, days: int) -> dict:
    """Generate cost report from the database."""
    engine = create_engine(db_url)
    
    since_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = text("""
        SELECT tenant_id, sum(total_cost_usd) as total_cost, count(*) as call_count
        FROM call_analytics
        WHERE created_at >= :since
        GROUP BY tenant_id
        ORDER BY total_cost DESC
    """)
    
    report = {
        "period_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_platform_cost": 0.0,
        "total_platform_calls": 0,
        "tenants": []
    }
    
    with engine.connect() as conn:
        result = conn.execute(query, {"since": since_date})
        for row in result:
            cost = float(row.total_cost or 0)
            calls = int(row.call_count or 0)
            report["tenants"].append({
                "tenant_id": row.tenant_id,
                "cost_usd": round(cost, 4),
                "calls": calls
            })
            report["total_platform_cost"] += cost
            report["total_platform_calls"] += calls
            
    report["total_platform_cost"] = round(report["total_platform_cost"], 4)
    return report

def post_to_slack(report: dict, webhook_url: str) -> None:
    """Post formatted report to Slack."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"💰 Weekly LLM Cost Report ({report['period_days']} Days)"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Total Platform Cost:* ${report['total_platform_cost']:.2f}\n*Total Calls:* {report['total_platform_calls']}"
            }
        },
        {"type": "divider"}
    ]
    
    # Add top 5 tenants
    top_tenants = report["tenants"][:5]
    if top_tenants:
        tenant_lines = []
        for i, t in enumerate(top_tenants, 1):
            tenant_lines.append(f"{i}. *Tenant `{t['tenant_id'][:8]}...`*: ${t['cost_usd']:.2f} ({t['calls']} calls)")
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Top Spend by Tenant:*\n" + "\n".join(tenant_lines)
            }
        })
        
    payload = {"blocks": blocks}
    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
    print("✅ Successfully posted to Slack.")

def main() -> None:
    parser = argparse.ArgumentParser(description="LLM Cost Reporter")
    parser.add_argument("--period-days", type=int, default=7)
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument("--format", type=str, choices=["json"], default="json")
    parser.add_argument("--report-file", type=str, help="Read from existing report file instead of generating")
    parser.add_argument("--post-to-slack", action="store_true")
    parser.add_argument("--check-budget", action="store_true")
    parser.add_argument("--daily-limit", type=float, default=500.0)
    parser.add_argument("--monthly-limit", type=float, default=10000.0)
    
    args = parser.parse_args()
    
    if args.report_file:
        with open(args.report_file, "r") as f:
            report = json.load(f)
    else:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("❌ DATABASE_URL environment variable required.", file=sys.stderr)
            sys.exit(1)
        report = generate_report(db_url, args.period_days)
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2)
            print(f"Report written to {args.output}")

    if args.post_to_slack:
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            print("❌ SLACK_WEBHOOK_URL environment variable required.", file=sys.stderr)
            sys.exit(1)
        post_to_slack(report, webhook_url)
        
    if args.check_budget:
        avg_daily = report["total_platform_cost"] / report["period_days"]
        projected_monthly = avg_daily * 30
        
        print(f"Average Daily Cost: ${avg_daily:.2f} (Limit: ${args.daily_limit})")
        print(f"Projected Monthly Cost: ${projected_monthly:.2f} (Limit: ${args.monthly_limit})")
        
        if avg_daily > args.daily_limit or projected_monthly > args.monthly_limit:
            print("🚨 Budget threshold exceeded!")
            sys.exit(1)
        else:
            print("✅ Within budget limits.")

if __name__ == "__main__":
    main()
