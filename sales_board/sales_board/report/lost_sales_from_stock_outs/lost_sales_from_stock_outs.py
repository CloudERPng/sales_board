import frappe
from frappe.utils import getdate

from sales_board.utils.data import col, fetch_orders
from sales_board.utils.inventory import balances, lines, location_of, locations, prepare, ret, settings


def execute(filters=None):
	return ret(build(prepare(filters)))


def build(f):
	s = settings()
	statuses = set(lines(s.get("no_stock_statuses")) or ["No Product", "No Stock"])
	cohort, _rev = fetch_orders(f.company, f.from_date, f.to_date, None, s)
	lost = [r for r in cohort if r.status in statuses]
	locs = locations(f.company, s)
	bal = balances(f.company, getdate(f.to_date))
	zone_stock, hq_stock, agent_stock = {}, 0.0, {}
	for (item, wh), b in bal.items():
		loc = location_of(locs, wh)
		if b.value <= 0:
			continue
		if loc.type == "HQ":
			hq_stock += b.value
		elif loc.type == "Agent":
			zone_stock[loc.zone] = zone_stock.get(loc.zone, 0) + b.value
			agent_stock[loc.agent] = agent_stock.get(loc.agent, 0) + b.value
	view = f.get("view_by") or "Zone"
	key = {"Zone": lambda r: r.zone, "State": lambda r: r.state_clean, "Product": lambda r: r.requested_category or "Not captured",
		"Delivery Agent": lambda r: r.agent}[view]
	g = {}
	valid = sum(r.valid for r in cohort)
	for r in lost:
		k = key(r)
		x = g.setdefault(k, frappe._dict(group=r.agent_label if view == "Delivery Agent" else k, zone=r.zone, orders=0,
			value=0.0, states=set()))
		x.orders += 1
		x.value += r.order_total
		x.states.add(r.state_clean)
	data = []
	for k, x in g.items():
		x.n_states = len(x.states)
		del x["states"]
		if view == "Zone":
			x.field_stock = zone_stock.get(k, 0)
		elif view == "State":
			x.field_stock = zone_stock.get(x.zone, 0)
		elif view == "Delivery Agent":
			x.field_stock = agent_stock.get(k, 0) if k else None
		data.append(x)
	data.sort(key=lambda x: -x.value)
	tot_v = sum(x.value for x in data)
	data.append(frappe._dict(group="Total", bold=1, orders=sum(x.orders for x in data), value=tot_v))
	columns = [col(view, "group", width=220)]
	if view == "State":
		columns.append(col("Zone", "zone", width=110))
	columns += [col("Orders Lost (No Stock)", "orders", "Int", 140), col("Value Lost", "value", "Currency", 140)]
	if view in ("Zone", "State"):
		columns.append(col("Agent Stock in Zone at Period End", "field_stock", "Currency", 200))
	if view == "Delivery Agent":
		columns.append(col("Agent's Stock at Period End", "field_stock", "Currency", 180))
	summary = [
		{"value": len(lost), "label": "Orders lost to no stock", "datatype": "Int", "indicator": "Red"},
		{"value": tot_v, "label": "Value lost", "datatype": "Currency", "indicator": "Red"},
		{"value": 100.0 * len(lost) / valid if valid else 0, "label": "Share of valid orders", "datatype": "Percent", "indicator": "Orange"},
		{"value": hq_stock, "label": "Stock at HQ (period end)", "datatype": "Currency", "indicator": "Blue"},
	]
	top = data[:-1][:12]
	chart = {"data": {"labels": [str(x.group) for x in top], "datasets": [{"name": "Value lost", "values": [x.value for x in top]}]},
		"type": "bar", "colors": ["#C0392B"]}
	return {"columns": columns, "data": data, "chart": chart, "report_summary": summary,
		"message": f"Orders placed in the period with status {', '.join(sorted(statuses))}. Where stock was held elsewhere "
			"in the same zone or at HQ, the sale was lost to allocation, not to a shortage. Statuses are set in Sales Board Settings."}
