import frappe
from frappe.utils import date_diff, getdate, today

from sales_board.utils.data import check_access, col, fetch_orders, settings
from sales_board.utils.runner import prepare

BUCKETS = [(1, "d0_1"), (3, "d2_3"), (7, "d4_7"), (10**6, "d8")]


def execute(filters=None):
	"""Live cash control: delivered orders vs Agent Collections. Never served from a snapshot."""
	check_access()
	f = prepare(filters)
	s = settings()
	_c, revenue = fetch_orders(f.company, f.from_date, f.to_date, f.branch, s)
	asof = getdate(today())
	if f.get("show_orders"):
		return order_view(revenue, asof)
	groups = {}
	for r in revenue:
		g = groups.setdefault(r.agent, frappe._dict(label=r.agent_label, delivered=0, value=0.0, remitted=0,
			net_collected=0.0, fees=0.0, discount=0.0, other_exp=0.0, in_progress=0.0, review=0, outstanding=0,
			outstanding_value=0.0, d0_1=0.0, d2_3=0.0, d4_7=0.0, d8=0.0, days_sum=0, days_n=0))
		g.delivered += 1
		g.value += r.order_total
		if r.coll_state == "Remitted":
			g.remitted += 1
			g.net_collected += r.net_collected
			g.fees += r.fee
			g.discount += r.discount
			g.other_exp += r.other_exp
			if r.days_to_remit is not None:
				g.days_sum += r.days_to_remit
				g.days_n += 1
		elif r.coll_state == "In progress":
			g.in_progress += r.order_total
		elif r.coll_state == "Needs review":
			g.review += 1
		else:
			g.outstanding += 1
			g.outstanding_value += r.order_total
			age = date_diff(asof, r.recog_date) if r.recog_date else 999
			for limit, fld in BUCKETS:
				if age <= limit:
					g[fld] += r.order_total
					break
	data = sorted(groups.values(), key=lambda g: -g.outstanding_value)
	for g in data:
		g.remit_rate = 100.0 * g.remitted / g.delivered if g.delivered else 0
		g.avg_days = round(g.days_sum / g.days_n, 1) if g.days_n else None
	tot = frappe._dict(label="Total", bold=1)
	for fld in ("delivered", "value", "remitted", "net_collected", "fees", "discount", "other_exp", "in_progress", "review",
		"outstanding", "outstanding_value", "d0_1", "d2_3", "d4_7", "d8", "days_sum", "days_n"):
		tot[fld] = sum(g[fld] for g in data)
	tot.remit_rate = 100.0 * tot.remitted / tot.delivered if tot.delivered else 0
	tot.avg_days = round(tot.days_sum / tot.days_n, 1) if tot.days_n else None
	data.append(tot)
	columns = [
		col("Delivery Agent", "label", width=230), col("Delivered", "delivered", "Int", 85),
		col("Order Value", "value", "Currency", 140), col("Remitted", "remitted", "Int", 85),
		col("Remitted %", "remit_rate", "Percent", 95), col("Net Remitted", "net_collected", "Currency", 140),
		col("Fees Deducted", "fees", "Currency", 120), col("Discounts", "discount", "Currency", 110),
		col("Other Expenses", "other_exp", "Currency", 115), col("In Progress", "in_progress", "Currency", 120),
		col("Needs Review", "review", "Int", 95), col("Not Remitted (Orders)", "outstanding", "Int", 130),
		col("Not Remitted (Value)", "outstanding_value", "Currency", 145), col("0-1 Days", "d0_1", "Currency", 115),
		col("2-3 Days", "d2_3", "Currency", 115), col("4-7 Days", "d4_7", "Currency", 115),
		col("Over 7 Days", "d8", "Currency", 120), col("Avg Days to Remit", "avg_days", "Float", 120),
	]
	summary = [
		{"value": tot.value, "label": "Delivered value", "datatype": "Currency", "indicator": "Blue"},
		{"value": tot.net_collected, "label": "Net remitted", "datatype": "Currency", "indicator": "Green"},
		{"value": tot.outstanding_value, "label": "Not yet remitted", "datatype": "Currency", "indicator": "Red"},
		{"value": tot.d8, "label": "Not remitted after 7 days", "datatype": "Currency", "indicator": "Red"},
		{"value": tot.avg_days, "label": "Avg days to remit", "datatype": "Float", "indicator": "Orange"},
	]
	return columns, data, ("Delivered orders matched to Agent Collections by CRM Order, else Sales Invoice. "
		"Age of unremitted cash is counted from the delivery date to today."), None, summary


def order_view(revenue, asof):
	rows = [r for r in revenue if r.coll_state in ("Not collected", "Needs review")]
	rows.sort(key=lambda r: (r.agent_label, r.recog_date or asof))
	data = [{"agent": r.agent_label, "order": r.name, "customer": r.customer_name, "state": r.state_clean,
		"delivered_on": r.actual_delivery_date, "age": date_diff(asof, r.recog_date) if r.recog_date else None,
		"value": r.order_total, "sales_invoice": r.sales_invoice, "status": r.coll_state} for r in rows]
	columns = [col("Delivery Agent", "agent", width=210), col("CRM Order", "order", "Link", 190, "CRM Order"),
		col("Customer", "customer", width=170), col("State", "state", width=110),
		col("Delivered On", "delivered_on", "Date", 105), col("Days Outstanding", "age", "Int", 115),
		col("Order Value", "value", "Currency", 120), col("Sales Invoice", "sales_invoice", "Link", 170, "Sales Invoice"),
		col("Collection Status", "status", width=130)]
	return columns, data, "Delivered orders with no remitted or in-progress collection.", None, None
