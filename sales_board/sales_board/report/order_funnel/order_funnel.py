from sales_board.utils.data import STAGES, col, fetch_orders, kpis, pct, settings, summary
from sales_board.utils.runner import run

REPORT = "Order Funnel"


def execute(filters=None):
	return run(REPORT, filters, build)


def build(f):
	s = settings()
	cohort, revenue = fetch_orders(f.company, f.from_date, f.to_date, f.branch, s)
	valid = sum(r.valid for r in cohort)
	total_value = sum(r.order_total for r in cohort)
	data = []
	for stage, meaning in STAGES:
		rows = [r for r in cohort if r.stage == stage]
		v = sum(r.order_total for r in rows)
		data.append({"stage": stage, "meaning": meaning, "orders": len(rows),
			"pct_valid": 0 if stage.startswith("Duplicate") else pct(len(rows), valid),
			"value": v, "pct_value": pct(v, total_value)})
	data.append({"stage": "Total", "orders": len(cohort), "pct_valid": 100 if valid else 0,
		"value": total_value, "pct_value": 100 if total_value else 0, "bold": 1})
	columns = [
		col("Stage", "stage", width=190), col("Meaning", "meaning", width=380),
		col("Orders", "orders", "Int", 90), col("% of Valid Orders", "pct_valid", "Percent", 120),
		col("Order Value", "value", "Currency", 150), col("% of Value", "pct_value", "Percent", 100),
	]
	chart = {"data": {"labels": [d["stage"] for d in data[:-1]],
		"datasets": [{"name": "Orders", "values": [d["orders"] for d in data[:-1]]}]},
		"type": "bar", "colors": ["#2E8B6E"]}
	return {"columns": columns, "data": data, "chart": chart, "report_summary": kpis(summary(cohort, revenue)),
		"message": "Orders placed in the period, by where each one stands now."}
