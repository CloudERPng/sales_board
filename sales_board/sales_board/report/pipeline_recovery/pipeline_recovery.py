import frappe
from frappe.utils import date_diff, getdate, today

from sales_board.utils.data import OPEN_STAGES, col, fetch_orders, settings
from sales_board.utils.runner import run

REPORT = "Pipeline Recovery"
BUCKETS = [(7, "age_0_7"), (14, "age_8_14"), (30, "age_15_30"), (10**6, "age_31")]
VIEWS = {
	"Closer": (lambda r: r.credit_closer, lambda r: r.credit_closer_label),
	"Delivery Agent": (lambda r: r.agent, lambda r: r.agent_label),
	"Marketer": (lambda r: r.marketer, lambda r: r.marketer_label),
}


def execute(filters=None):
	return run(REPORT, filters, build)


def build(f):
	s = settings()
	view = f.get("view_by") or "Closer"
	key, label = VIEWS.get(view, VIEWS["Closer"])
	cohort, _rev = fetch_orders(f.company, f.from_date, f.to_date, f.branch, s)
	open_rows = [r for r in cohort if r.stage in OPEN_STAGES]
	asof = getdate(today())
	groups = {}
	for r in open_rows:
		k = key(r)
		g = groups.setdefault(k, frappe._dict(label=label(r), with_closer=0, stalled=0, transit=0, total=0,
			age_0_7=0, age_8_14=0, age_15_30=0, age_31=0, fresh_value=0.0, value=0.0))
		g.total += 1
		g.value += r.order_total
		if r.stage == "Open with closer":
			g.with_closer += 1
		elif r.stage == "Stalled with agent":
			g.stalled += 1
		else:
			g.transit += 1
		age = date_diff(asof, r.order_day) if r.order_day else 999
		for limit, field in BUCKETS:
			if age <= limit:
				g[field] += 1
				break
		if age <= 14:
			g.fresh_value += r.order_total
	data = sorted(groups.values(), key=lambda g: -g.value)
	tot = frappe._dict(label="Total", bold=1)
	for fld in ("with_closer", "stalled", "transit", "total", "age_0_7", "age_8_14", "age_15_30", "age_31", "fresh_value", "value"):
		tot[fld] = sum(g[fld] for g in data)
	data.append(tot)
	columns = [
		col(view, "label", width=230), col("Open with Closer", "with_closer", "Int", 115),
		col("Stalled with Agent", "stalled", "Int", 120), col("In Transit", "transit", "Int", 85),
		col("Total Open", "total", "Int", 90), col("0-7 Days Old", "age_0_7", "Int", 95),
		col("8-14 Days", "age_8_14", "Int", 85), col("15-30 Days", "age_15_30", "Int", 85),
		col("Over 30 Days", "age_31", "Int", 95), col("Fresh Value (≤14 days)", "fresh_value", "Currency", 160),
		col("Total Open Value", "value", "Currency", 150),
	]
	summary = [
		{"value": tot.total, "label": "Open orders", "datatype": "Int", "indicator": "Orange"},
		{"value": tot.value, "label": "Open value", "datatype": "Currency", "indicator": "Orange"},
		{"value": tot.fresh_value, "label": "Fresh value (≤14 days)", "datatype": "Currency", "indicator": "Green"},
	]
	return {"columns": columns, "data": data, "report_summary": summary,
		"message": "Orders placed in the period that are neither delivered nor lost. Age is counted to today; chase the fresh value first."}
