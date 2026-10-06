from frappe.utils import cint

from sales_board.utils.data import col, aggregate, fetch_orders, kpis, rank, settings, summary, total_row
from sales_board.utils.runner import run

REPORT = "Closer Scorecard"
FIELDS = ["label", "main_attr", "valid", "calls_per_order", "dispatched", "delivered", "conversion", "success", "failed",
	"fail_rate", "lost_pre", "open", "open_value", "revenue", "deliveries", "aov", "upsell_attach", "upsell_value", "rank"]


def execute(filters=None):
	return run(REPORT, filters, build)


def build(f):
	s = settings()
	cohort, revenue = fetch_orders(f.company, f.from_date, f.to_date, f.branch, s)
	rows = aggregate(cohort, revenue, key=lambda r: r.credit_closer, label=lambda r: r.credit_closer_label,
		attr=lambda r: r.branch or "")
	rank(rows, "valid", cint(s.min_closer_orders), "conversion")
	rows.sort(key=lambda x: -x.revenue)
	rows.append(total_row(rows, sum(r.rev_value for r in revenue)))
	data = [{k: x.get(k) for k in FIELDS + ["bold"]} for x in rows]
	columns = [
		col("Closer", "label", width=220), col("Main Branch", "main_attr", width=110),
		col("Valid Orders", "valid", "Int", 95), col("Calls per Order", "calls_per_order", "Float", 105),
		col("Dispatched", "dispatched", "Int", 90), col("Delivered", "delivered", "Int", 85),
		col("Conversion %", "conversion", "Percent", 105), col("Delivery Success %", "success", "Percent", 125),
		col("Failed After Dispatch", "failed", "Int", 120), col("Failed %", "fail_rate", "Percent", 85),
		col("Lost Before Dispatch", "lost_pre", "Int", 120), col("Still Open", "open", "Int", 85),
		col("Open Value", "open_value", "Currency", 130), col("Revenue Recognised", "revenue", "Currency", 150),
		col("Deliveries", "deliveries", "Int", 90), col("Avg Order Value", "aov", "Currency", 120),
		col("Upsell Attach %", "upsell_attach", "Percent", 110), col("Upsell Value", "upsell_value", "Currency", 120),
		col("Rank (Conversion)", "rank", "Int", 110),
	]
	return {"columns": columns, "data": data, "report_summary": kpis(summary(cohort, revenue)),
		"message": "Orders that went through the follow-up pool are credited to the follow-up closer. "
			"'Failed after dispatch' = confirmed by the closer, then refused at the door."}
