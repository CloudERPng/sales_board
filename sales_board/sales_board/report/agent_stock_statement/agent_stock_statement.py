import frappe
from frappe.utils import add_days, getdate

from sales_board.utils.data import col
from sales_board.utils.inventory import (FLOW_FIELDS, balances, blank_flow, item_names, keep, location_of, locations,
	movements, prepare, ret, settings)

QTY = ["opening", "received", "customer_returns", "other_in", "sold", "transfer_out", "other_out", "adj_qty", "closing",
	"difference"]


def execute(filters=None):
	return ret(build(prepare(filters)))


def build(f):
	s = settings()
	locs = locations(f.company, s)
	fd, td = getdate(f.from_date), getdate(f.to_date)
	open_bal = balances(f.company, add_days(fd, -1))
	close_bal = balances(f.company, td)
	flows = movements(f.company, fd, td)
	view = f.get("view_by") or "Location"
	keys = set(open_bal) | set(close_bal) | set(flows)
	names = item_names([k[0] for k in keys])
	groups = {}
	for item, wh in keys:
		loc = location_of(locs, wh)
		if not keep(loc, f) or (f.get("item_code") and item != f.item_code):
			continue
		o = open_bal.get((item, wh)) or frappe._dict(qty=0, value=0)
		c = close_bal.get((item, wh)) or frappe._dict(qty=0, value=0)
		m = flows.get((item, wh)) or blank_flow()
		key = (wh, item) if view == "Location × Item" else item if view == "Item" else wh
		g = groups.setdefault(key, frappe._dict(
			location=loc.label if view != "Item" else "", type=loc.type if view != "Item" else "",
			state=loc.state if view != "Item" else "", item=item if view != "Location" else "",
			item_name=names.get(item, "") if view != "Location" else "",
			**{k: 0.0 for k in QTY}, opening_value=0.0, received_value=0.0, sold_value=0.0, adj_value=0.0,
			reval_value=0.0, closing_value=0.0))
		g.opening += o.qty
		g.opening_value += o.value
		g.received += m.transfer_in + m.purchased + m.opening_entry
		g.received_value += m.transfer_in_value + m.purchased_value + m.opening_entry_value
		g.customer_returns += m.customer_returns
		g.other_in += m.other_in
		g.sold += m.sold
		g.sold_value += m.sold_value
		g.transfer_out += m.transfer_out
		g.other_out += m.other_out
		g.adj_qty += m.adj_qty
		g.adj_value += m.adj_qty_value
		g.reval_value += m.reval_value
		g.closing += c.qty
		g.closing_value += c.value
	data = []
	for g in groups.values():
		expected = g.opening + g.received + g.customer_returns + g.other_in - g.sold - g.transfer_out - g.other_out + g.adj_qty
		g.difference = round(g.closing - expected, 3)
		g.sell_through = 100.0 * g.sold / (g.opening + g.received) if (g.opening + g.received) > 0 else None
		if any(abs(g[k]) > 1e-9 for k in QTY + ["closing_value"]):
			data.append(g)
	data.sort(key=lambda x: -x.closing_value)
	tot = frappe._dict(location="Total" if view != "Item" else "", item="Total" if view == "Item" else "", bold=1)
	for k in QTY + ["opening_value", "received_value", "sold_value", "adj_value", "reval_value", "closing_value"]:
		tot[k] = sum(x[k] for x in data)
	tot.sell_through = 100.0 * tot.sold / (tot.opening + tot.received) if (tot.opening + tot.received) > 0 else None
	data.append(tot)
	columns = []
	if view != "Item":
		columns += [col("Location", "location", width=220), col("Type", "type", width=75), col("State", "state", width=105)]
	if view != "Location":
		columns += [col("Item", "item", "Link", 130, "Item"), col("Item Name", "item_name", width=180)]
	columns += [
		col("Opening Qty", "opening", "Float", 95), col("Received", "received", "Float", 90),
		col("Customer Returns", "customer_returns", "Float", 110), col("Other In", "other_in", "Float", 80),
		col("Delivered (Sold)", "sold", "Float", 105), col("Transferred Out", "transfer_out", "Float", 110),
		col("Other Out", "other_out", "Float", 85), col("Count Adjustment", "adj_qty", "Float", 115),
		col("Closing Qty", "closing", "Float", 95), col("Unexplained", "difference", "Float", 95),
		col("Sell-through %", "sell_through", "Percent", 105), col("Opening Value", "opening_value", "Currency", 130),
		col("Received Value", "received_value", "Currency", 130), col("Cost of Deliveries", "sold_value", "Currency", 135),
		col("Adjustment Value", "adj_value", "Currency", 130), col("Revaluation", "reval_value", "Currency", 120),
		col("Closing Value", "closing_value", "Currency", 135),
	]
	summary = [
		{"value": tot.opening_value, "label": "Opening value", "datatype": "Currency", "indicator": "Blue"},
		{"value": tot.received_value, "label": "Received", "datatype": "Currency", "indicator": "Green"},
		{"value": tot.sold_value, "label": "Cost of deliveries", "datatype": "Currency", "indicator": "Blue"},
		{"value": tot.adj_value, "label": "Count adjustments", "datatype": "Currency",
			"indicator": "Red" if tot.adj_value < 0 else "Green"},
		{"value": tot.closing_value, "label": "Closing value", "datatype": "Currency", "indicator": "Blue"},
	]
	return {"columns": columns, "data": data, "report_summary": summary,
		"message": "What each location should be holding: opening + received + returns − deliveries − transfers out "
			"± count adjustments = closing. 'Count Adjustment' is stock found short or over at a stock count; "
			"'Revaluation' is a cost change with no quantity effect. 'Unexplained' should be nil."}
