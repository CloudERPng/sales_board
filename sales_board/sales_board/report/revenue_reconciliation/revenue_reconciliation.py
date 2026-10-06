import frappe
from frappe.utils import cint, getdate

from sales_board.utils.data import col, fetch_orders, kpis, settings, summary
from sales_board.utils.runner import run

REPORT = "Revenue Reconciliation"


def execute(filters=None):
	return run(REPORT, filters, build)


def _n(rows):
	return len(rows), sum(r.order_total for r in rows)


def build(f):
	s = settings()
	fd, td = getdate(f.from_date), getdate(f.to_date)
	cohort, revenue = fetch_orders(f.company, fd, td, f.branch, s)
	dup = [r for r in cohort if r.stage == "Duplicate (invalid)"]
	lost = [r for r in cohort if r.stage in ("Lost before dispatch", "Failed after dispatch")]
	rev_after = [r for r in cohort if r.stage == "Reversed after delivery"]
	open_ = [r for r in cohort if r.stage in ("Open with closer", "Stalled with agent", "In transit with agent")]
	won = [r for r in cohort if r.won]
	won_in = [r for r in won if r.recog_date and fd <= r.recog_date <= td]
	won_after = [r for r in won if not (r.recog_date and fd <= r.recog_date <= td)]
	earlier = [r for r in revenue if r.order_day and r.order_day < fd]
	no_date = [r for r in revenue if r.missing_delivery_date]
	inv_names = list({r.sales_invoice for r in revenue if r.sales_invoice})
	submitted = set()
	for i in range(0, len(inv_names), 1000):
		submitted |= set(frappe.get_all("Sales Invoice", filters={"name": ["in", inv_names[i:i + 1000]], "docstatus": 1}, pluck="name"))
	invoiced = [r for r in revenue if r.sales_invoice in submitted]
	not_invoiced = [r for r in revenue if r.sales_invoice not in submitted]

	def line(label, rows, sign=1, comment="", bold=0):
		n, v = _n(rows)
		return {"line": label, "orders": sign * n, "value": sign * v, "comment": comment, "bold": bold}

	rc, rv = _n(cohort)
	dc, dv = _n(dup)
	data = [
		line("Orders received in the period (all statuses)", cohort, comment="Gross order intake"),
		line("Less: duplicates", dup, -1, "Excluded from conversion"),
		{"line": "Valid orders", "orders": rc - dc, "value": rv - dv, "bold": 1},
		line("Less: lost (cancelled / rejected / no stock)", lost, -1, "See Order Funnel for before vs after dispatch"),
		line("Less: reversed after delivery", rev_after, -1, "Delivered, then cancelled or returned"),
		line("Less: still open", open_, -1, "See Pipeline Recovery"),
		line("Period orders delivered (to date)", won, bold=1),
		line("   of which delivered within the period", won_in),
		line("   of which delivered after the period end", won_after, comment="Revenue of the following period"),
		line("Add: earlier orders delivered in the period", earlier, comment="Opening pipeline converted"),
		line("Revenue recognised in the period (order value)", revenue, bold=1, comment="Orders delivered in the period, whenever placed"),
	]
	disc = sum(r.discount for r in revenue)
	if cint(s.revenue_net_of_discounts):
		data += [
			{"line": "Less: discounts given at delivery", "value": -disc, "comment": "From Agent Collections"},
			{"line": "Net revenue recognised", "value": sum(r.rev_value for r in revenue), "bold": 1},
		]
	data += [
		{"line": "", "orders": None, "value": None},
		{"line": "Controls", "bold": 1},
		line("Recognised orders with no Actual Delivery Date", no_date,
			comment="Recognised on last-updated date instead; ask agents to complete the field"),
		line("Recognised orders with a submitted Sales Invoice", invoiced),
		line("Recognised orders without a submitted Sales Invoice", not_invoiced,
			comment="Should be nil if every delivery is invoiced in the ERP"),
		{"line": "", "orders": None, "value": None},
		{"line": "Agent remittance (order value)", "bold": 1},
		line("Remitted", [r for r in revenue if r.coll_state == "Remitted"], comment="Collection completed"),
		line("Remittance in progress", [r for r in revenue if r.coll_state == "In progress"], comment="Declared, cash not yet received"),
		line("Collection needs review", [r for r in revenue if r.coll_state == "Needs review"]),
		line("Not yet remitted", [r for r in revenue if r.coll_state == "Not collected"], comment="Cash still with agents: see Agent Remittance"),
		{"line": "Net cash remitted", "value": sum(r.net_collected for r in revenue), "comment": "After fees, discounts and other expenses"},
		{"line": "Delivery fees: actual from collections", "value": sum(r.fee for r in revenue if r.fee_actual)},
		{"line": "Delivery fees: estimated (no collection yet)", "value": sum(r.fee for r in revenue if not r.fee_actual),
			"comment": "Agent Delivery Fee on the order, else the default in Settings"},
		{"line": "Other expenses deducted by agents", "value": sum(r.other_exp for r in revenue)},
	]
	diff = len(won_in) + len(earlier) - len(revenue)
	if diff:
		data.append({"line": "Unexplained difference", "orders": diff, "comment": "Investigate", "bold": 1})
	columns = [col("Line", "line", width=380), col("Orders", "orders", "Int", 100),
		col("Value", "value", "Currency", 160), col("Comment", "comment", width=380)]
	return {"columns": columns, "data": data, "report_summary": kpis(summary(cohort, revenue))}
