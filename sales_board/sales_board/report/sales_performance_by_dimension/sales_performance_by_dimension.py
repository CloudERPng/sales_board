import frappe
from frappe.utils import add_days, cint, flt, get_datetime, getdate

from sales_board.utils.data import col, aggregate, fetch_orders, fetch_spend, finish, kpis, pkey, settings, spend_note, summary, total_row
from sales_board.utils.runner import run

REPORT = "Sales Performance by Dimension"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BANDS = [(0, "Below 20,000"), (20000, "20,000 - 24,999"), (25000, "25,000 - 29,999"), (30000, "30,000 - 39,999"),
	(40000, "40,000 - 59,999"), (60000, "60,000 and above")]
TIME_DIMS = {"Order Date", "Order Week", "Weekday", "Hour of Day", "Order Value Band", "Units per Order"}
FIELDS = ["label", "orders", "valid", "dispatched", "delivered", "conversion", "success", "failed", "fail_rate", "open",
	"open_value", "delivered_value", "revenue", "deliveries", "share", "aov", "units_per_order"]


def _band(v):
	idx = 0
	for i, (lo, _l) in enumerate(BANDS):
		if flt(v) >= lo:
			idx = i
	return idx


def dimension(name):
	"""Return (key, label) functions; keys sort naturally for time-like dimensions."""
	if name == "Product":
		return (lambda r: r.requested_category or "Not captured"), None
	if name == "State":
		return (lambda r: r.state_clean), None
	if name == "Zone":
		return (lambda r: r.zone), None
	if name == "Branch":
		return (lambda r: r.branch or "Unassigned"), None
	if name == "Lead Channel":
		return (lambda r: r.lead_channel or "Not captured"), None
	if name == "Lead Source":
		return (lambda r: (r.lead_source or "Not captured").strip()), None
	if name == "UTM Campaign":
		return (lambda r: r.utm_campaign or "(no campaign tag)"), None
	if name == "CRM Status":
		return (lambda r: r.status or "Not set"), None
	if name == "Order Date":
		return (lambda r: str(r.order_day or "")), None
	if name == "Order Week":
		def wk(r):
			if not r.order_day:
				return ""
			d = getdate(r.order_day)
			return str(add_days(d, -d.weekday()))
		return wk, (lambda r: f"Week of {wk(r)}")
	if name == "Weekday":
		k = lambda r: getdate(r.order_day).weekday() if r.order_day else 9
		return k, (lambda r: WEEKDAYS[k(r)] if k(r) < 7 else "Not captured")
	if name == "Hour of Day":
		k = lambda r: get_datetime(r.order_date).hour if r.order_date else 99
		return k, (lambda r: f"{k(r):02d}:00 - {k(r):02d}:59" if k(r) < 24 else "Not captured")
	if name == "Online vs Manual":
		return (lambda r: "Online lead (web form)" if cint(r.online_lead) else "Manually entered"), None
	if name == "Order Value Band":
		return (lambda r: _band(r.order_total)), (lambda r: BANDS[_band(r.order_total)][1])
	if name == "Units per Order":
		k = lambda r: min(cint(flt(r.total_qty)), 6)
		return k, (lambda r: "6 or more units" if k(r) >= 6 else f"{k(r)} unit(s)")
	return (lambda r: "All"), None


def execute(filters=None):
	return run(REPORT, filters, build)


def build(f):
	s = settings()
	dim = f.get("group_by") or "Product"
	cohort, revenue = fetch_orders(f.company, f.from_date, f.to_date, f.branch, s)
	key, label = dimension(dim)
	rows = aggregate(cohort, revenue, key=key, label=label or key)
	spend_dims = {"Product": lambda e: pkey(e.product_category) or "Not captured",
		"Order Date": lambda e: str(getdate(e.spend_date)),
		"Order Week": lambda e: str(add_days(getdate(e.spend_date), -getdate(e.spend_date).weekday()))}
	show_spend = dim in spend_dims and not f.get("branch")
	if show_spend:
		sp = {}
		for e in fetch_spend(f.from_date, f.to_date):
			k_ = spend_dims[dim](e)
			sp[k_] = sp.get(k_, 0) + flt(e.amount_spent)
		total_rev = sum(r.rev_value for r in revenue)
		for x in rows:
			x.spend = sp.pop(pkey(x.key) if dim == "Product" else x.key, 0.0)
			finish(x, total_rev)
		unmatched = sum(sp.values())
	if dim in TIME_DIMS:
		rows.sort(key=lambda x: x.key)
	else:
		rows.sort(key=lambda x: (-x.revenue, -x.orders))
	rows.append(total_row(rows, sum(r.rev_value for r in revenue)))
	fields = FIELDS + (["spend", "cpl", "cpa", "roas"] if show_spend else [])
	data = [{k: x.get(k) for k in fields + ["bold"]} for x in rows]
	columns = [
		col(dim, "label", width=230), col("Orders", "orders", "Int", 80), col("Valid", "valid", "Int", 80),
		col("Dispatched", "dispatched", "Int", 90), col("Delivered", "delivered", "Int", 85),
		col("Conversion %", "conversion", "Percent", 105), col("Delivery Success %", "success", "Percent", 125),
		col("Failed After Dispatch", "failed", "Int", 120), col("Failed %", "fail_rate", "Percent", 85),
		col("Still Open", "open", "Int", 85), col("Open Value", "open_value", "Currency", 130),
		col("Delivered Value (Period Orders)", "delivered_value", "Currency", 170),
		col("Revenue Recognised", "revenue", "Currency", 150), col("Deliveries", "deliveries", "Int", 90),
		col("Revenue Share %", "share", "Percent", 110), col("Avg Order Value", "aov", "Currency", 120),
		col("Units per Order", "units_per_order", "Float", 100),
	]
	if show_spend:
		columns += [col("Ad Spend", "spend", "Currency", 130), col("Cost per Valid Lead", "cpl", "Currency", 125),
			col("Cost per Delivered Order", "cpa", "Currency", 145), col("ROAS", "roas", "Float", 80)]
	body = [x for x in rows if not x.get("bold")]
	chart_rows = body if dim in TIME_DIMS else body[:15]
	chart = {"data": {"labels": [str(x.label) for x in chart_rows],
		"datasets": [{"name": "Orders", "values": [x.orders for x in chart_rows]},
			{"name": "Delivered", "values": [x.delivered for x in chart_rows]}]},
		"type": "line" if dim in ("Order Date", "Order Week", "Hour of Day") else "bar", "colors": ["#E9A23B", "#1F5F3F"]}
	msg = "Orders, conversion and open figures use orders placed in the period; revenue uses orders delivered in the period."
	if show_spend:
		msg += " ROAS = delivered value of period orders ÷ spend."
		if unmatched:
			msg += f" {frappe.format_value(unmatched, 'Currency')} of spend matched no row (see Marketing ROAS)."
		msg += " " + spend_note(f)
	if dim == "Zone":
		msg += " 'Unmapped' = a state spelling not yet in Sales Board Settings: add it under State Spelling Variants."
	return {"columns": columns, "data": data, "chart": chart, "report_summary": kpis(summary(cohort, revenue)), "message": msg}
