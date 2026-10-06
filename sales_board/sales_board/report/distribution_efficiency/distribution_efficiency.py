import frappe
from frappe.utils import add_days, date_diff, getdate

from sales_board.utils.data import col, fetch_orders, pct
from sales_board.utils.inventory import (balances, blank_flow, keep, location_of, locations, movements, prepare, ret,
	settings)

ZONES = ["North Central", "North East", "North West", "South East", "South South", "South West"]


def execute(filters=None):
	return ret(build(prepare(filters)))


def replenishments(company, fd, td):
	rows = frappe.db.sql("""select sed.t_warehouse as wh, count(distinct se.name) as n
		from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
		where se.docstatus = 1 and se.company = %(c)s and se.posting_date between %(fd)s and %(td)s
			and se.purpose = 'Material Transfer' and ifnull(sed.t_warehouse, '') != ''
		group by sed.t_warehouse""", {"c": company, "fd": fd, "td": td}, as_dict=True)
	return {r.wh: r.n for r in rows}


def build(f):
	s = settings()
	locs = locations(f.company, s)
	fd, td = getdate(f.from_date), getdate(f.to_date)
	ndays = date_diff(td, fd) + 1
	ob, cb = balances(f.company, add_days(fd, -1)), balances(f.company, td)
	flows = movements(f.company, fd, td)
	repl = replenishments(f.company, fd, td)
	cohort, _rev = fetch_orders(f.company, fd, td, None, s)
	crm = {}
	for r in cohort:
		if r.valid and r.dispatched:
			c = crm.setdefault(r.agent, [0, 0, 0])
			c[0] += 1
			c[1] += r.won
			c[2] += 1 if r.stage == "Failed after dispatch" else 0
	g = {}
	for key in set(ob) | set(cb) | set(flows):
		item, wh = key
		loc = location_of(locs, wh)
		if loc.type == "Transit" or not keep(loc, f) or (f.get("item_code") and item != f.item_code):
			continue
		o, c = ob.get(key) or frappe._dict(qty=0, value=0), cb.get(key) or frappe._dict(qty=0, value=0)
		m = flows.get(key) or blank_flow()
		x = g.setdefault(wh, frappe._dict(location=loc.label, type=loc.type, state=loc.state, zone=loc.zone, agent=loc.agent,
			opening=0.0, received=0.0, sold=0.0, closing=0.0, open_value=0.0, close_value=0.0, received_value=0.0,
			sold_value=0.0, adj_value=0.0))
		x.opening += o.qty
		x.closing += c.qty
		x.open_value += o.value
		x.close_value += c.value
		x.received += m.transfer_in + m.purchased + m.opening_entry
		x.received_value += m.transfer_in_value + m.purchased_value + m.opening_entry_value
		x.sold += m.sold - m.customer_returns
		x.sold_value += m.sold_value - m.customer_returns_value
		x.adj_value += m.adj_qty_value
	data = []
	for wh, x in g.items():
		avg_value = (x.open_value + x.close_value) / 2
		avg_qty = (x.opening + x.closing) / 2
		x.sell_through = pct(x.sold, x.opening + x.received) if (x.opening + x.received) > 0 else None
		x.turnover = x.sold_value / avg_value if avg_value > 0 else None
		x.days_held = avg_qty / (x.sold / ndays) if x.sold > 0 else None
		x.replenishments = repl.get(wh, 0)
		x.shrinkage = pct(-x.adj_value, x.sold_value) if x.sold_value and x.adj_value < 0 else 0
		d = crm.get(x.agent) if x.agent else None
		x.dispatched, x.delivered, x.failed = d if d else (None, None, None)
		x.success = pct(x.delivered, x.dispatched) if d else None
		x.stock_per_delivery = x.close_value / x.delivered if d and x.delivered else None
		if x.opening or x.received or x.sold or x.closing:
			data.append(x)
	view = f.get("view_by") or "Location"
	if view == "Zone":
		return zone_view(data, cohort, f)
	data.sort(key=lambda x: -(x.sold_value or 0))
	tot = frappe._dict(location="Total", bold=1)
	for k in ("opening", "received", "sold", "closing", "open_value", "close_value", "received_value", "sold_value",
		"adj_value", "replenishments"):
		tot[k] = sum(x[k] or 0 for x in data)
	tot.sell_through = pct(tot.sold, tot.opening + tot.received)
	avg = (tot.open_value + tot.close_value) / 2
	tot.turnover = tot.sold_value / avg if avg else None
	tot.days_held = ((tot.opening + tot.closing) / 2) / (tot.sold / ndays) if tot.sold else None
	tot.shrinkage = pct(-tot.adj_value, tot.sold_value) if tot.adj_value < 0 else 0
	data.append(tot)
	columns = [
		col("Location", "location", width=220), col("Type", "type", width=75), col("State", "state", width=105),
		col("Opening Qty", "opening", "Float", 95), col("Received Qty", "received", "Float", 100),
		col("Delivered Qty", "sold", "Float", 100), col("Closing Qty", "closing", "Float", 95),
		col("Sell-through %", "sell_through", "Percent", 105), col("Stock Turns", "turnover", "Float", 90),
		col("Avg Days Stock Held", "days_held", "Float", 130), col("Replenishments", "replenishments", "Int", 110),
		col("Cost of Deliveries", "sold_value", "Currency", 135), col("Closing Value", "close_value", "Currency", 130),
		col("Stock Value per Delivery", "stock_per_delivery", "Currency", 150),
		col("Shrinkage %", "shrinkage", "Percent", 95), col("Orders Dispatched", "dispatched", "Int", 115),
		col("Delivered Orders", "delivered", "Int", 110), col("Delivery Success %", "success", "Percent", 125),
	]
	top = [x for x in data if not x.get("bold")][:15]
	chart = {"data": {"labels": [x.location for x in top], "datasets": [
		{"name": "Received", "values": [x.received for x in top]}, {"name": "Delivered", "values": [x.sold for x in top]}]},
		"type": "bar", "colors": ["#E9A23B", "#1F5F3F"]}
	summary = [
		{"value": tot.sell_through, "label": "Sell-through", "datatype": "Percent", "indicator": "Blue"},
		{"value": tot.turnover, "label": "Stock turns in period", "datatype": "Float", "indicator": "Blue"},
		{"value": tot.days_held, "label": "Avg days stock held", "datatype": "Float", "indicator": "Orange"},
		{"value": tot.shrinkage, "label": "Shrinkage (of cost delivered)", "datatype": "Percent", "indicator": "Red"},
	]
	return {"columns": columns, "data": data, "chart": chart, "report_summary": summary,
		"message": "Sell-through = delivered ÷ (opening + received). Stock turns = cost of deliveries ÷ average stock value. "
			"Stock value per delivery shows how much stock is parked to support each delivery. "
			"Delivery success comes from CRM orders dispatched to the agent in the period."}


def zone_view(rows, cohort, f):
	stock, sold = {}, {}
	for x in rows:
		z = x.zone or ("HQ" if x.type == "HQ" else "Not captured")
		stock[z] = stock.get(z, 0) + x.close_value
		sold[z] = sold.get(z, 0) + x.sold_value
	orders, deliv = {}, {}
	for r in cohort:
		if r.valid:
			orders[r.zone] = orders.get(r.zone, 0) + 1
			deliv[r.zone] = deliv.get(r.zone, 0) + r.won
	ts, to, td_, tsold = sum(v for k, v in stock.items() if k != "HQ"), sum(orders.values()), sum(deliv.values()), sum(sold.values())
	data = []
	for z in ZONES + ["Not captured", "HQ"]:
		if not (stock.get(z) or orders.get(z)):
			continue
		ss = pct(stock.get(z, 0), ts) if z != "HQ" else None
		os_ = pct(orders.get(z, 0), to) if z != "HQ" else None
		data.append(frappe._dict(zone=z, stock_value=stock.get(z, 0), stock_share=ss, orders=orders.get(z, 0),
			order_share=os_, delivered=deliv.get(z, 0), delivered_share=pct(deliv.get(z, 0), td_) if z != "HQ" else None,
			gap=(ss - os_) if ss is not None and os_ is not None else None, sold_value=sold.get(z, 0)))
	data.append(frappe._dict(zone="Total", bold=1, stock_value=sum(stock.values()), orders=to, delivered=td_, sold_value=tsold))
	z = [x for x in data if x.zone not in ("HQ", "Total")]
	chart = {"data": {"labels": [x.zone for x in z], "datasets": [
		{"name": "Share of field stock %", "values": [round(x.stock_share or 0, 1) for x in z]},
		{"name": "Share of orders %", "values": [round(x.order_share or 0, 1) for x in z]}]},
		"type": "bar", "colors": ["#2E8B6E", "#E9A23B"]}
	return {"data": data, "chart": chart, "columns": [
		col("Zone", "zone", width=150), col("Stock Value (Period End)", "stock_value", "Currency", 160),
		col("Share of Field Stock %", "stock_share", "Percent", 140), col("Valid Orders", "orders", "Int", 100),
		col("Share of Orders %", "order_share", "Percent", 125), col("Delivered", "delivered", "Int", 90),
		col("Share of Deliveries %", "delivered_share", "Percent", 140),
		col("Stock vs Demand Gap (pts)", "gap", "Float", 160), col("Cost of Deliveries", "sold_value", "Currency", 140)],
		"report_summary": [], "message": "A positive gap means the zone holds more of the field stock than its share of "
			"orders: stock parked away from demand. A negative gap means demand is likely to run out of stock first."}
