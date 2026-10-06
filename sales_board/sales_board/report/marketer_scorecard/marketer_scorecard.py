from frappe.utils import cint, flt

from sales_board.utils.data import (UNASSIGNED, _blank, aggregate, col, fetch_orders, fetch_spend, finish, kpis,
	marketer_name, mkey, rank, settings, spend_kpis, spend_note, summary, total_row)
from sales_board.utils.runner import run

REPORT = "Marketer Scorecard"
FIELDS = ["label", "orders", "duplicates", "dup_rate", "valid", "dispatched", "delivered", "conversion", "success",
	"failed", "fail_rate", "open", "open_value", "spend", "cpl", "cpa", "delivered_value", "roas", "revenue",
	"deliveries", "share", "aov", "rank"]


def execute(filters=None):
	return run(REPORT, filters, build)


def build(f):
	s = settings()
	cohort, revenue = fetch_orders(f.company, f.from_date, f.to_date, f.branch, s)
	rows = aggregate(cohort, revenue, key=lambda r: r.marketer, label=lambda r: r.marketer_label)
	spend = [] if f.get("branch") else fetch_spend(f.from_date, f.to_date)
	by_m = {}
	for e in spend:
		by_m[mkey(e.digital_marketer)] = by_m.get(mkey(e.digital_marketer), 0) + flt(e.amount_spent)
	total_rev = sum(r.rev_value for r in revenue)
	for x in rows:
		x.spend = by_m.pop(mkey(x.key), 0.0)
		finish(x, total_rev)
	for m, amt in by_m.items():  # spend with no leads in the period
		x = _blank(m, marketer_name(m))
		x.spend = amt
		rows.append(finish(x, total_rev))
	rank(rows, "valid", cint(s.min_marketer_leads), "conversion")
	rows.sort(key=lambda x: (-x.revenue, -x.spend))
	rows.append(total_row(rows, total_rev))
	data = [{k: x.get(k) for k in FIELDS + ["bold"]} for x in rows]
	columns = [
		col("Digital Marketer", "label", width=220), col("Leads", "orders", "Int", 80),
		col("Duplicates", "duplicates", "Int", 90), col("Duplicate %", "dup_rate", "Percent", 95),
		col("Valid Leads", "valid", "Int", 90), col("Dispatched", "dispatched", "Int", 90),
		col("Delivered", "delivered", "Int", 85), col("Conversion %", "conversion", "Percent", 105),
		col("Delivery Success %", "success", "Percent", 125), col("Failed After Dispatch", "failed", "Int", 120),
		col("Failed %", "fail_rate", "Percent", 85), col("Still Open", "open", "Int", 85),
		col("Open Value", "open_value", "Currency", 130), col("Ad Spend", "spend", "Currency", 130),
		col("Cost per Valid Lead", "cpl", "Currency", 125), col("Cost per Delivered Order", "cpa", "Currency", 145),
		col("Delivered Value (Period Leads)", "delivered_value", "Currency", 170), col("ROAS", "roas", "Float", 80),
		col("Revenue Recognised", "revenue", "Currency", 150), col("Deliveries", "deliveries", "Int", 90),
		col("Revenue Share %", "share", "Percent", 110), col("Avg Order Value", "aov", "Currency", 120),
		col("Rank (Conversion)", "rank", "Int", 110),
	]
	top = [x for x in rows if not x.get("bold")][:12]
	chart = {"data": {"labels": [x.label for x in top], "datasets": [
		{"name": "Ad spend", "values": [x.spend for x in top]},
		{"name": "Delivered value", "values": [x.delivered_value for x in top]}]},
		"type": "bar", "colors": ["#E07A5F", "#1F5F3F"]}
	msg = ("ROAS = delivered value of leads placed in the period ÷ ad spend in the period. For the current month it rises as "
		"open orders convert. Spend comes from Marketing Spend, matched on the marketer's user. " + spend_note(f))
	return {"columns": columns, "data": data, "chart": chart,
		"report_summary": kpis(summary(cohort, revenue)) + ([] if f.get("branch") else spend_kpis(cohort, spend)), "message": msg}
