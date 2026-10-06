import frappe

from sales_board.utils.data import col
from sales_board.utils.inventory import (LOCATION_TYPES, balances, item_names, keep, location_of, locations, prepare,
	ret, settings)


def execute(filters=None):
	return ret(build(prepare(filters, need_period=False)))


def build(f):
	s = settings()
	locs = locations(f.company, s)
	bal = balances(f.company, f.as_of)
	view = f.get("view_by") or "Location"
	names = item_names([k[0] for k in bal])
	groups = {}
	total_value = 0.0
	for (item, wh), b in bal.items():
		loc = location_of(locs, wh)
		if not keep(loc, f) or (f.get("item_code") and item != f.item_code):
			continue
		if not (b.qty or b.value):
			continue
		total_value += b.value
		if view == "Location × Item":
			key = (wh, item)
		elif view == "Item":
			key = item
		elif view == "Zone":
			key = loc.zone or ("HQ" if loc.type == "HQ" else "Not captured")
		elif view == "Location Type":
			key = loc.type
		else:
			key = wh
		g = groups.setdefault(key, frappe._dict(location=loc.label if view in ("Location", "Location × Item") else "",
			type=loc.type if view in ("Location", "Location × Item") else "", state=loc.state if view in ("Location", "Location × Item") else "",
			zone=loc.zone if view in ("Location", "Location × Item") else "",
			item=item if view in ("Item", "Location × Item") else "", item_name=names.get(item, "") if view in ("Item", "Location × Item") else "",
			group=key if view in ("Zone", "Location Type") else "", qty=0.0, value=0.0, item_set=set(), loc_set=set(), negative=0))
		g.qty += b.qty
		g.value += b.value
		if b.qty > 0:
			g.item_set.add(item)
			g.loc_set.add(wh)
		if b.qty < 0:
			g.negative += 1
	data = []
	for g in groups.values():
		g.share = 100.0 * g.value / total_value if total_value else 0
		g.n_items, g.n_locations = len(g.item_set), len(g.loc_set)
		del g["item_set"], g["loc_set"]
		data.append(g)
	data.sort(key=lambda x: (LOCATION_TYPES.index(x.group) if view == "Location Type" and x.group in LOCATION_TYPES else 0, -x.value))
	tot = frappe._dict(location="Total" if view in ("Location", "Location × Item") else "", item="Total" if view == "Item" else "",
		group="Total" if view in ("Zone", "Location Type") else "", bold=1,
		qty=sum(x.qty for x in data), value=total_value, share=100 if total_value else 0,
		negative=sum(x.negative for x in data))
	data.append(tot)
	columns = []
	if view in ("Zone", "Location Type"):
		columns.append(col(view, "group", width=180))
	if view in ("Location", "Location × Item"):
		columns += [col("Location", "location", width=220), col("Type", "type", width=80), col("State", "state", width=110),
			col("Zone", "zone", width=110)]
	if view in ("Item", "Location × Item"):
		columns += [col("Item", "item", "Link", 140, "Item"), col("Item Name", "item_name", width=200)]
	columns += [col("Qty", "qty", "Float", 100), col("Stock Value", "value", "Currency", 150),
		col("% of Stock Value", "share", "Percent", 120)]
	if view not in ("Location × Item",):
		if view != "Item":
			columns.append(col("Items Held", "n_items", "Int", 90))
		if view not in ("Location",):
			columns.append(col("Locations Holding", "n_locations", "Int", 120))
	columns.append(col("Negative Balances", "negative", "Int", 120))
	by_type = {}
	for (item, wh), b in bal.items():
		loc = location_of(locs, wh)
		if keep(loc, f) and (not f.get("item_code") or item == f.item_code):
			by_type[loc.type] = by_type.get(loc.type, 0) + b.value
	chart = {"data": {"labels": [t for t in LOCATION_TYPES if by_type.get(t)],
		"datasets": [{"name": "Stock value", "values": [by_type[t] for t in LOCATION_TYPES if by_type.get(t)]}]},
		"type": "donut", "colors": ["#1F5F3F", "#E9A23B", "#2E8B6E", "#9C9C9C"]}
	neg = tot.negative
	summary = [
		{"value": total_value, "label": "Stock value", "datatype": "Currency", "indicator": "Blue"},
		{"value": 100.0 * by_type.get("Agent", 0) / total_value if total_value else 0, "label": "Held by agents",
			"datatype": "Percent", "indicator": "Orange"},
		{"value": by_type.get("HQ", 0), "label": "At HQ", "datatype": "Currency", "indicator": "Green"},
		{"value": by_type.get("Transit", 0), "label": "In transit", "datatype": "Currency", "indicator": "Blue"},
		{"value": neg, "label": "Negative balances", "datatype": "Int", "indicator": "Red" if neg else "Green"},
	]
	msg = ("Negative balances mean sales were posted from a location that had no stock in the system: the physical "
		"stock is somewhere else or the receipt was never posted.") if neg else ""
	if not (s.get("hq_warehouses") or []):
		msg += " No HQ warehouses are set in Sales Board Settings, so HQ stock shows as 'Other'."
	return {"columns": columns, "data": data, "chart": chart, "report_summary": summary, "message": msg.strip()}
