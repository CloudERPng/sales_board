import frappe
from frappe.utils import date_diff, flt, getdate

from sales_board.utils.data import col
from sales_board.utils.inventory import balances, item_names, keep, last_dates, location_of, locations, prepare, ret, settings


def execute(filters=None):
	return ret(build(prepare(filters)))


def legs(company, fd, td):
	has_transit = frappe.db.has_column("Stock Entry", "add_to_transit")
	has_out = frappe.db.has_column("Stock Entry", "outgoing_stock_entry")
	return frappe.db.sql(f"""select se.name, se.posting_date, se.owner,
			{'se.add_to_transit' if has_transit else '0'} as to_transit,
			{'se.outgoing_stock_entry' if has_out else 'NULL'} as outgoing,
			sed.item_code, sed.s_warehouse, sed.t_warehouse, sed.transfer_qty as qty,
			ifnull(sed.basic_amount, sed.amount) as value
		from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
		where se.docstatus = 1 and se.company = %(c)s and se.purpose = 'Material Transfer'
			and se.posting_date between %(fd)s and %(td)s""", {"c": company, "fd": getdate(fd), "td": getdate(td)}, as_dict=True)


def build(f):
	s = settings()
	locs = locations(f.company, s)
	view = f.get("view_by") or "Route"
	if view == "Still in transit":
		return in_transit(f, s, locs)
	rows = legs(f.company, f.from_date, f.to_date)
	first_leg_date = {}
	if rows:
		outs = list({r.outgoing for r in rows if r.outgoing})
		for i in range(0, len(outs), 500):
			for x in frappe.get_all("Stock Entry", filters={"name": ["in", outs[i:i + 500]]}, fields=["name", "posting_date"]):
				first_leg_date[x.name] = x.posting_date
	g = {}
	for r in rows:
		if f.get("item_code") and r.item_code != f.item_code:
			continue
		src, dst = location_of(locs, r.s_warehouse), location_of(locs, r.t_warehouse)
		if view == "Destination":
			if not keep(dst, f):
				continue
			key, label = r.t_warehouse, dst.label
		elif view == "Source":
			if not keep(src, f):
				continue
			key, label = r.s_warehouse, src.label
		else:
			if f.get("warehouse") and f.warehouse not in (r.s_warehouse, r.t_warehouse):
				continue
			key = label = f"{src.type} → {dst.type}"
		x = g.setdefault(key, frappe._dict(group=label, state=(dst.state if view == "Destination" else src.state if view == "Source" else ""),
			type=(dst.type if view == "Destination" else src.type if view == "Source" else ""),
			entries=set(), qty=0.0, value=0.0, transit_days=0, transit_n=0, partners=set()))
		x.entries.add(r.name)
		x.qty += flt(r.qty)
		x.value += flt(r.value)
		x.partners.add(r.s_warehouse if view == "Destination" else r.t_warehouse)
		if r.outgoing and first_leg_date.get(r.outgoing):
			x.transit_days += date_diff(r.posting_date, first_leg_date[r.outgoing])
			x.transit_n += 1
	data = []
	for x in g.values():
		x.n_entries, x.n_partners = len(x.entries), len(x.partners)
		x.avg_transit = round(x.transit_days / x.transit_n, 1) if x.transit_n else None
		x.avg_value = x.value / x.n_entries if x.n_entries else 0
		for k in ("entries", "partners", "transit_days", "transit_n"):
			del x[k]
		data.append(x)
	data.sort(key=lambda x: -x.value)
	data.append(frappe._dict(group="Total", bold=1, n_entries=sum(x.n_entries for x in data), qty=sum(x.qty for x in data),
		value=sum(x.value for x in data)))
	label = {"Route": "Route (from → to)", "Destination": "Receiving Location", "Source": "Sending Location"}[view]
	columns = [col(label, "group", width=230)]
	if view != "Route":
		columns += [col("Type", "type", width=75), col("State", "state", width=105)]
	columns += [col("Transfers", "n_entries", "Int", 90), col("Qty Moved", "qty", "Float", 100),
		col("Value Moved", "value", "Currency", 140), col("Avg Value per Transfer", "avg_value", "Currency", 150),
		col("Sending Locations" if view == "Destination" else "Receiving Locations", "n_partners", "Int", 130),
		col("Avg Days in Transit", "avg_transit", "Float", 130)]
	top = data[:-1][:12]
	chart = {"data": {"labels": [x.group for x in top], "datasets": [{"name": "Value moved", "values": [x.value for x in top]}]},
		"type": "bar", "colors": ["#2E8B6E"]}
	return {"columns": columns, "data": data, "chart": chart,
		"message": "Each leg of a transfer counts separately: HQ → Transit is the dispatch, Transit → Agent is the receipt. "
			"Avg days in transit is measured on the receiving leg."}


def in_transit(f, s, locs):
	bal = balances(f.company, f.to_date)
	last = last_dates(f.company, f.to_date)
	names = item_names([k[0] for k in bal])
	asof = getdate(f.to_date)
	data = []
	for (item, wh), b in bal.items():
		loc = location_of(locs, wh)
		if loc.type != "Transit" or b.qty <= 0 or (f.get("item_code") and item != f.item_code):
			continue
		ld = last.get((item, wh))
		data.append(frappe._dict(group=loc.label, item=item, item_name=names.get(item, ""), qty=b.qty, value=b.value,
			since=date_diff(asof, ld.last_receipt) if ld and ld.last_receipt else None))
	data.sort(key=lambda x: -(x.since or 0))
	data.append(frappe._dict(group="Total", bold=1, qty=sum(x.qty for x in data), value=sum(x.value for x in data)))
	return {"data": data, "columns": [col("Transit Warehouse", "group", width=220), col("Item", "item", "Link", 130, "Item"),
		col("Item Name", "item_name", width=180), col("Qty in Transit", "qty", "Float", 110),
		col("Value in Transit", "value", "Currency", 140), col("Days Since Last Dispatch", "since", "Int", 160)],
		"report_summary": [{"value": data[-1].value, "label": "Value in transit", "datatype": "Currency", "indicator": "Orange"}],
		"message": "Stock sitting in transit warehouses at the To Date. Anything in transit for more than a few days "
			"was dispatched but not received by the agent."}
