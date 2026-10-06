import frappe
from frappe.utils import flt, getdate

from sales_board.utils.data import col, pct
from sales_board.utils.inventory import (adjustments, item_names, keep, location_of, locations, movements, prepare, ret,
	settings)


def execute(filters=None):
	return ret(build(prepare(filters)))


def build(f):
	s = settings()
	large = flt(s.get("large_adjustment_value") or 100000)
	locs = locations(f.company, s)
	rows = adjustments(f.company, f.from_date, f.to_date)
	names = item_names([r.item_code for r in rows])
	view = f.get("view_by") or "Location"
	kept = []
	for r in rows:
		loc = location_of(locs, r.warehouse)
		if not keep(loc, f) or (f.get("item_code") and r.item_code != f.item_code):
			continue
		if f.get("kind") and r.kind != f.kind:
			continue
		r.large = 1 if abs(r.qty_value) >= large else 0
		if f.get("large_only") and not r.large:
			continue
		r.loc = loc
		kept.append(r)
	if view == "Detail":
		data = [frappe._dict(voucher=r.voucher, posting_date=r.posting_date, owner=r.owner, location=r.loc.label,
			state=r.loc.state, item=r.item_code, item_name=names.get(r.item_code, ""), kind=r.kind, system_qty=r.current_qty,
			counted_qty=r.qty, dq=r.dq, qty_value=r.qty_value, reval_value=r.reval_value, large="Yes" if r.large else "")
			for r in sorted(kept, key=lambda r: (r.qty_value))]
		columns = [col("Stock Reconciliation", "voucher", "Link", 170, "Stock Reconciliation"), col("Date", "posting_date", "Date", 95),
			col("Posted By", "owner", "Link", 170, "User"), col("Location", "location", width=200), col("State", "state", width=100),
			col("Item", "item", "Link", 120, "Item"), col("Item Name", "item_name", width=160), col("Type", "kind", width=120),
			col("System Qty", "system_qty", "Float", 90), col("Counted Qty", "counted_qty", "Float", 95),
			col("Difference", "dq", "Float", 90), col("Qty Effect (₦)", "qty_value", "Currency", 130),
			col("Revaluation (₦)", "reval_value", "Currency", 130), col("Large", "large", width=65)]
		return finish({"columns": columns, "data": data}, kept, large)
	sold = {}
	if view == "Location":
		for (item, wh), m in movements(f.company, f.from_date, f.to_date).items():
			sold[wh] = sold.get(wh, 0) + m.sold_value - m.customer_returns_value
	keyf = {"Location": lambda r: r.warehouse, "Item": lambda r: r.item_code,
		"Month": lambda r: getdate(r.posting_date).strftime("%Y-%m"), "Posted By": lambda r: r.owner}[view]
	g = {}
	for r in kept:
		k = keyf(r)
		x = g.setdefault(k, frappe._dict(group=r.loc.label if view == "Location" else names.get(k, k) if view == "Item" else k,
			item=k if view == "Item" else "", type=r.loc.type if view == "Location" else "",
			state=r.loc.state if view == "Location" else "", docs=set(), lines=0, short_qty=0.0, short_value=0.0,
			excess_qty=0.0, excess_value=0.0, reval_value=0.0, large=0, opening_value=0.0))
		x.docs.add(r.voucher)
		x.lines += 1
		x.large += r.large
		if r.is_opening:
			x.opening_value += r.total_value
			continue
		if r.dq < 0:
			x.short_qty += -r.dq
			x.short_value += -r.qty_value
		elif r.dq > 0:
			x.excess_qty += r.dq
			x.excess_value += r.qty_value
		x.reval_value += r.reval_value
	data = []
	for k, x in g.items():
		x.n_docs = len(x.docs)
		del x["docs"]
		x.net_value = x.excess_value - x.short_value
		if view == "Location":
			x.throughput = sold.get(k, 0)
			x.shrinkage = pct(x.short_value - x.excess_value, x.throughput) if x.throughput else None
		data.append(x)
	data.sort(key=lambda x: x.net_value if view != "Month" else 0)
	if view == "Month":
		data.sort(key=lambda x: x.group)
	tot = frappe._dict(group="Total", bold=1)
	for k in ("n_docs", "lines", "short_qty", "short_value", "excess_qty", "excess_value", "net_value", "reval_value", "large",
		"opening_value", "throughput"):
		tot[k] = sum(x.get(k) or 0 for x in data)
	if view == "Location" and tot.throughput:
		tot.shrinkage = pct(tot.short_value - tot.excess_value, tot.throughput)
	data.append(tot)
	label = {"Location": "Location", "Item": "Item", "Month": "Month", "Posted By": "Posted By"}[view]
	columns = [col(label, "group", width=220)]
	if view == "Item":
		columns.append(col("Item Code", "item", "Link", 130, "Item"))
	if view == "Location":
		columns += [col("Type", "type", width=75), col("State", "state", width=105)]
	columns += [col("Documents", "n_docs", "Int", 90), col("Lines", "lines", "Int", 70),
		col("Shortage Qty", "short_qty", "Float", 100), col("Shortage Value", "short_value", "Currency", 135),
		col("Excess Qty", "excess_qty", "Float", 90), col("Excess Value", "excess_value", "Currency", 125),
		col("Net Count Effect", "net_value", "Currency", 140), col("Revaluation", "reval_value", "Currency", 125),
		col("Large Adjustments", "large", "Int", 120), col("Opening Stock Entries", "opening_value", "Currency", 145)]
	if view == "Location":
		columns += [col("Cost of Deliveries", "throughput", "Currency", 140), col("Shrinkage %", "shrinkage", "Percent", 100)]
	chart = None
	if view == "Month":
		body = data[:-1]
		chart = {"data": {"labels": [x.group for x in body], "datasets": [
			{"name": "Shortages", "values": [-x.short_value for x in body]}, {"name": "Excess found", "values": [x.excess_value for x in body]}]},
			"type": "bar", "barOptions": {"stacked": 1}, "colors": ["#C0392B", "#2E8B6E"]}
	elif view in ("Location", "Posted By", "Item"):
		worst = [x for x in data[:-1] if x.net_value < 0][:12]
		chart = {"data": {"labels": [x.group for x in worst], "datasets": [{"name": "Net shortage", "values": [-x.net_value for x in worst]}]},
			"type": "bar", "colors": ["#C0392B"]}
	return finish({"columns": columns, "data": data, "chart": chart}, kept, large)


def finish(res, kept, large):
	short = sum(-r.qty_value for r in kept if r.dq < 0 and not r.is_opening)
	excess = sum(r.qty_value for r in kept if r.dq > 0 and not r.is_opening)
	reval = sum(r.reval_value for r in kept if not r.is_opening)
	res["report_summary"] = [
		{"value": short, "label": "Shortages", "datatype": "Currency", "indicator": "Red"},
		{"value": excess, "label": "Excess found", "datatype": "Currency", "indicator": "Green"},
		{"value": excess - short, "label": "Net count effect", "datatype": "Currency", "indicator": "Red" if excess < short else "Green"},
		{"value": reval, "label": "Revaluations (no qty change)", "datatype": "Currency", "indicator": "Blue"},
		{"value": sum(r.large for r in kept), "label": f"Large (≥ {frappe.format_value(large, 'Currency')})", "datatype": "Int", "indicator": "Orange"},
	]
	res["message"] = ("Submitted Stock Reconciliations only. Each line is split into its count effect (counted qty − system qty, "
		"at the existing rate) and its revaluation (a cost change), so cost corrections are not mistaken for stock losses. "
		"Shrinkage % = net shortage ÷ cost of deliveries from that location.")
	return res
