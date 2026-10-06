import frappe
from frappe.utils import cint, date_diff, flt, getdate

from sales_board.utils.data import col
from sales_board.utils.inventory import (balances, cover_status, item_names, keep, last_dates, location_of, locations,
	prepare, ret, sales_rate, settings)

STATUSES = ["Stock-out", "Understocked", "Healthy", "Overstocked", "Slow", "Idle"]


def execute(filters=None):
	return ret(build(prepare(filters, need_period=False)))


def rows_for(f, s):
	locs = locations(f.company, s)
	days = cint(f.get("lookback") or s.get("cover_lookback_days") or 30)
	bal = balances(f.company, f.as_of)
	rate = sales_rate(f.company, f.as_of, days)
	last = last_dates(f.company, f.as_of)
	asof = getdate(f.as_of)
	names = item_names([k[0] for k in set(bal) | set(rate)])
	out = []
	for key in set(bal) | set(rate):
		item, wh = key
		loc = location_of(locs, wh)
		if loc.type in ("Transit",) or not keep(loc, f) or (f.get("item_code") and item != f.item_code):
			continue
		b = bal.get(key) or frappe._dict(qty=0, value=0)
		daily, daily_cost = rate.get(key, (0, 0))
		ld = last.get(key)
		since = date_diff(asof, ld.last_sale) if ld and ld.last_sale else None
		if b.qty <= 0 and daily <= 0:
			continue
		status, cover = cover_status(b.qty, daily, s, since)
		out.append(frappe._dict(warehouse=wh, location=loc.label, type=loc.type, state=loc.state, zone=loc.zone,
			item=item, item_name=names.get(item, ""), qty=b.qty, value=b.value, daily=daily, daily_cost=daily_cost,
			cover=cover, status=status, last_sale=ld.last_sale if ld else None,
			last_receipt=ld.last_receipt if ld else None, since=since))
	return out, days


def build(f):
	s = settings()
	rows, days = rows_for(f, s)
	view = f.get("view_by") or "Location × Item"
	counts = {k: 0 for k in STATUSES}
	for r in rows:
		counts[r.status] = counts.get(r.status, 0) + 1
	if view == "Rebalancing suggestions":
		res = rebalance(rows, s)
	elif view == "Location":
		res = by_location(rows)
	else:
		if f.get("status"):
			rows = [r for r in rows if r.status == f.status]
		rows.sort(key=lambda r: (STATUSES.index(r.status) if r.status in STATUSES else 9, -(r.daily or 0)))
		res = {"data": rows, "columns": [
			col("Location", "location", width=210), col("State", "state", width=100), col("Item", "item", "Link", 130, "Item"),
			col("Item Name", "item_name", width=170), col("Qty", "qty", "Float", 80), col("Stock Value", "value", "Currency", 125),
			col(f"Avg Sold / Day ({days}d)", "daily", "Float", 120), col("Days of Cover", "cover", "Float", 105),
			col("Status", "status", width=115), col("Last Sale", "last_sale", "Date", 100),
			col("Last Receipt", "last_receipt", "Date", 105)]}
	res["chart"] = {"data": {"labels": STATUSES, "datasets": [{"name": "Location-items", "values": [counts[k] for k in STATUSES]}]},
		"type": "bar", "colors": ["#C0392B"]}
	res["report_summary"] = [
		{"value": counts["Stock-out"], "label": "Stock-outs (selling, no stock)", "datatype": "Int", "indicator": "Red"},
		{"value": counts["Understocked"], "label": f"Under {flt(s.understock_days or 5):g} days", "datatype": "Int", "indicator": "Orange"},
		{"value": counts["Healthy"], "label": "Healthy", "datatype": "Int", "indicator": "Green"},
		{"value": counts["Overstocked"], "label": f"Over {flt(s.overstock_days or 45):g} days", "datatype": "Int", "indicator": "Orange"},
		{"value": sum(r.value for r in rows if r.status in ("Idle", "Slow")), "label": "Value not selling", "datatype": "Currency", "indicator": "Red"},
	]
	res["message"] = (f"Days of cover = stock ÷ average daily deliveries over the last {days} days, per location and item. "
		"Thresholds are in Sales Board Settings.")
	return res


def by_location(rows):
	g = {}
	for r in rows:
		x = g.setdefault(r.warehouse, frappe._dict(location=r.location, type=r.type, state=r.state, zone=r.zone, value=0.0,
			daily_cost=0.0, **{k.lower().replace("-", "_"): 0 for k in STATUSES}))
		x.value += r.value
		x.daily_cost += r.daily_cost
		x[r.status.lower().replace("-", "_")] += 1
	data = []
	for x in g.values():
		x.cover = x.value / x.daily_cost if x.daily_cost else None
		x.slow_idle = x.slow + x.idle
		data.append(x)
	data.sort(key=lambda x: (-(x.stock_out + x.understocked), -x.value))
	return {"data": data, "columns": [
		col("Location", "location", width=220), col("Type", "type", width=75), col("State", "state", width=105),
		col("Zone", "zone", width=110), col("Stock Value", "value", "Currency", 130),
		col("Cost Delivered / Day", "daily_cost", "Currency", 140), col("Days of Cover (Value)", "cover", "Float", 140),
		col("Stock-outs", "stock_out", "Int", 90), col("Understocked", "understocked", "Int", 105),
		col("Healthy", "healthy", "Int", 80), col("Overstocked", "overstocked", "Int", 100),
		col("Slow / Idle Items", "slow_idle", "Int", 115)]}


def rebalance(rows, s):
	"""Suggest moves of each item from over-stocked / idle locations to stock-outs / under-stocked ones, same zone first."""
	under, over = flt(s.understock_days or 5), flt(s.overstock_days or 45)
	target = (under + over) / 2
	donors, needs = {}, []
	for r in rows:
		if r.type == "HQ":
			continue
		if r.status == "Overstocked":
			spare = r.qty - target * r.daily
		elif r.status in ("Idle", "Slow"):
			spare = r.qty
		else:
			spare = 0
		if spare >= 1:
			donors.setdefault(r.item, []).append([r, int(spare)])
		if r.status in ("Stock-out", "Understocked"):
			need = int(round(target * r.daily - max(r.qty, 0)))
			if need >= 1:
				needs.append([r, need])
	needs.sort(key=lambda n: -n[0].daily)
	data = []
	for n in needs:
		r, need = n
		pool = sorted(donors.get(r.item, []), key=lambda d: (d[0].zone != r.zone, d[0].state != r.state, -d[1]))
		for d in pool:
			if need <= 0:
				break
			if d[1] <= 0:
				continue
			mv = min(need, d[1])
			d[1] -= mv
			need -= mv
			data.append(frappe._dict(item=r.item, item_name=r.item_name, from_location=d[0].location,
				from_state=d[0].state, from_status=d[0].status, to_location=r.location, to_state=r.state, status=r.status,
				qty=mv, same_zone="Yes" if d[0].zone == r.zone else "No", to_cover=r.cover))
		if need > 0:
			data.append(frappe._dict(item=r.item, item_name=r.item_name, from_location="HQ (no spare stock in the field)",
				to_location=r.location, to_state=r.state, status=r.status, qty=need, same_zone=""))
	return {"data": data, "columns": [
		col("Item", "item", "Link", 120, "Item"), col("Item Name", "item_name", width=160),
		col("Move From", "from_location", width=210), col("From State", "from_state", width=100),
		col("From Status", "from_status", width=105), col("Move To", "to_location", width=210),
		col("To State", "to_state", width=100), col("Status", "status", width=110), col("Suggested Qty", "qty", "Int", 105),
		col("Same Zone", "same_zone", width=85)]}
