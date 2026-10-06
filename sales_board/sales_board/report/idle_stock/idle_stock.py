import frappe
from frappe.utils import cint, date_diff, getdate

from sales_board.utils.data import col
from sales_board.utils.inventory import balances, item_names, keep, last_dates, location_of, locations, prepare, ret, settings

BANDS = [(30, "31-60 days"), (60, "61-90 days"), (90, "Over 90 days")]


def execute(filters=None):
	return ret(build(prepare(filters, need_period=False)))


def build(f):
	s = settings()
	idle = cint(s.get("idle_days") or 30)
	locs = locations(f.company, s)
	bal = balances(f.company, f.as_of)
	last = last_dates(f.company, f.as_of)
	asof = getdate(f.as_of)
	names = item_names([k[0] for k in bal])
	data, bands = [], {}
	for key, b in bal.items():
		item, wh = key
		loc = location_of(locs, wh)
		if loc.type in ("HQ", "Transit") or b.qty <= 0 or not keep(loc, f) or (f.get("item_code") and item != f.item_code):
			continue
		ld = last.get(key)
		since_sale = date_diff(asof, ld.last_sale) if ld and ld.last_sale else None
		since_receipt = date_diff(asof, ld.last_receipt) if ld and ld.last_receipt else None
		age = since_sale if since_sale is not None else since_receipt
		if age is None or age <= idle:
			continue
		band = "Never sold here" if since_sale is None else next((l for lim, l in reversed(BANDS) if age > lim), "Up to 30 days")
		bands[band] = bands.get(band, 0) + b.value
		data.append(frappe._dict(location=loc.label, type=loc.type, state=loc.state, item=item, item_name=names.get(item, ""),
			qty=b.qty, value=b.value, last_sale=ld.last_sale if ld else None, last_receipt=ld.last_receipt if ld else None,
			since_sale=since_sale, since_receipt=since_receipt, band=band, agent_status=loc.agent_status))
	data.sort(key=lambda x: -x.value)
	total = sum(x.value for x in data)
	data.append(frappe._dict(location="Total", bold=1, qty=sum(x.qty for x in data), value=total))
	order = ["Up to 30 days"] + [l for _x, l in BANDS] + ["Never sold here"]
	chart = {"data": {"labels": [b for b in order if bands.get(b)], "datasets": [{"name": "Idle value", "values": [bands[b] for b in order if bands.get(b)]}]},
		"type": "bar", "colors": ["#E07A5F"]}
	columns = [
		col("Location", "location", width=220), col("Type", "type", width=75), col("State", "state", width=105),
		col("Agent Status", "agent_status", width=100), col("Item", "item", "Link", 130, "Item"),
		col("Item Name", "item_name", width=170), col("Qty", "qty", "Float", 80), col("Stock Value", "value", "Currency", 130),
		col("Last Sale", "last_sale", "Date", 100), col("Days Since Sale", "since_sale", "Int", 110),
		col("Last Receipt", "last_receipt", "Date", 105), col("Days Since Receipt", "since_receipt", "Int", 125),
		col("Idle Band", "band", width=120)]
	summary = [{"value": total, "label": "Idle stock value", "datatype": "Currency", "indicator": "Red"},
		{"value": len(data) - 1, "label": "Location-items idle", "datatype": "Int", "indicator": "Orange"},
		{"value": sum(x.value for x in data if x.get("agent_status") in ("Inactive", "Unavailable")),
			"label": "Held by inactive agents", "datatype": "Currency", "indicator": "Red"}]
	return {"columns": columns, "data": data, "chart": chart, "report_summary": summary,
		"message": f"Field stock (HQ and transit excluded) with no delivery for more than {idle} days (set in Sales Board Settings). Stock with inactive "
			"or unavailable agents should be recalled first."}
