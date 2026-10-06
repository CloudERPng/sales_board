"""Shared data layer for every Sales Board report.

Two sets of orders are used for any period:
  cohort  - orders PLACED in the period (drives the funnel and conversion)
  revenue - orders DELIVERED in the period (drives revenue recognised), whenever they were placed
"""
import re

import frappe
from frappe.utils import add_days, cint, date_diff, flt, getdate

STAGES = [
	("Delivered", "Paid and completed"),
	("Reversed after delivery", "Delivered, then cancelled or returned"),
	("In transit with agent", "With the agent and moving: accepted, notified, in progress, rescheduled"),
	("Stalled with agent", "With the agent, but customer not picking / not ready / call back"),
	("Open with closer", "Not yet dispatched; the closer is still working it"),
	("Failed after dispatch", "Cancelled or rejected after stock went out: a wasted trip"),
	("Lost before dispatch", "Cancelled / rejected / no stock before dispatch"),
	("Duplicate (invalid)", "Excluded from conversion"),
]
OPEN_STAGES = ("In transit with agent", "Stalled with agent", "Open with closer")
UNASSIGNED = "Unassigned"

CORE = ["name", "order_date", "status", "company", "order_total", "total_qty"]
OPTIONAL = [
	"lead_channel", "lead_source", "online_lead", "utm_campaign", "requested_category", "branch",
	"customer_name", "primary_phone", "state", "city", "upsell_value", "cross_sell_value", "has_upsell",
	"has_cross_sell", "closer", "closer_name", "followup_closer", "followup_closer_name", "digital_marketer",
	"marketer_name", "portal_agent", "portal_agent_name", "agent_delivery_fee", "actual_delivery_date",
	"agent_assignment_date", "confirmation_date", "last_updated_at", "call_attempts", "sales_invoice",
	"failure_reason", "modified",
]


def settings():
	return frappe.get_cached_doc("Sales Board Settings")


def pct(a, b):
	return 100.0 * flt(a) / flt(b) if flt(b) else 0.0


def clean(x):
	return re.sub(r"\s+", " ", x or "").strip()


def norm(x):
	return re.sub(r"\s+", " ", (x or "").replace("-", " ").replace(".", "")).strip().lower()


def check_access():
	roles = set(frappe.get_roles())
	if not roles.intersection({"Management", "System Manager"}):
		frappe.throw("Sales Board reports are restricted to the Management role.", frappe.PermissionError)


# ---------------------------------------------------------------- loading

def _select_list():
	cols = []
	for f in CORE + OPTIONAL:
		if f in CORE or frappe.db.has_column("CRM Order", f):
			cols.append(f"`{f}`")
		else:
			cols.append(f"NULL as `{f}`")
	return ", ".join(cols)


def _recog_expr():
	parts = [f for f in ("actual_delivery_date",) if frappe.db.has_column("CRM Order", f)]
	if frappe.db.has_column("CRM Order", "last_updated_at"):
		parts.append("DATE(last_updated_at)")
	parts.append("DATE(modified)")
	return "COALESCE(" + ", ".join(parts) + ")"


def won_statuses(s):
	return tuple(r.crm_status for r in s.status_map if r.status_type == "Won") or ("Delivered",)


def fetch_orders(company, from_date, to_date, branch=None, s=None):
	"""Return (cohort, revenue) lists of enriched order dicts."""
	s = s or settings()
	fd, td = getdate(from_date), getdate(to_date)
	args = {"company": company, "fd": fd, "td": td, "td_next": add_days(td, 1), "won": won_statuses(s), "branch": branch}
	branch_cond = " and branch = %(branch)s" if branch else ""
	sel = _select_list()
	cohort = frappe.db.sql(
		f"""select {sel} from `tabCRM Order`
		where company = %(company)s and order_date >= %(fd)s and order_date < %(td_next)s {branch_cond}""",
		args, as_dict=True)
	revenue = frappe.db.sql(
		f"""select {sel} from `tabCRM Order`
		where company = %(company)s and status in %(won)s
		and {_recog_expr()} between %(fd)s and %(td)s {branch_cond}""",
		args, as_dict=True)
	cohort, revenue = enrich(cohort, s), enrich(revenue, s)
	attach_collections(revenue, s, fd)
	return cohort, revenue


# ---------------------------------------------------------------- agent collections

def _lines(x):
	return [l.strip() for l in (x or "").splitlines() if l.strip()]


def collection_states(s):
	return {"Remitted": _lines(s.remitted_statuses) or ["Completed"],
		"In progress": _lines(s.in_progress_statuses) or ["Pending", "Awaiting Payment"],
		"Needs review": _lines(s.review_statuses) or ["Needs Review"]}


def attach_collections(revenue, s, fd):
	"""Attach actual agent deductions and remittance status from Agent Collection to delivered orders.

	Matched by CRM Order ID on the collection line, else by Sales Invoice. Collections with any other
	status (Draft, Failed, Reversed, Discarded) or cancelled documents are ignored.
	"""
	for r in revenue:
		r.coll_state, r.fee_actual, r.discount, r.other_exp, r.net_collected, r.days_to_remit = (
			"Not collected", 0, 0.0, 0.0, 0.0, None)
		r.rev_value = r.order_total
	if not revenue or not frappe.db.exists("DocType", "Agent Collection Invoice"):
		return
	states = collection_states(s)
	status_of = {st: k for k, sts in states.items() for st in sts}
	lines = frappe.db.sql(
		"""select ac.name as collection, ac.status, ac.collection_date, aci.crm_order, aci.sales_invoice,
			aci.delivery_fee, aci.discount, aci.other_expenses, aci.collection_amount
		from `tabAgent Collection Invoice` aci
		join `tabAgent Collection` ac on ac.name = aci.parent and aci.parenttype = 'Agent Collection'
		where ac.docstatus < 2 and ac.status in %(st)s and ac.collection_date >= %(fd)s""",
		{"st": tuple(status_of), "fd": add_days(getdate(fd), -7)}, as_dict=True)
	by_order, by_inv = {}, {}
	for l in lines:
		if l.crm_order:
			by_order.setdefault(l.crm_order.strip(), []).append(l)
		elif l.sales_invoice:
			by_inv.setdefault(l.sales_invoice, []).append(l)
	rank_ = {"Remitted": 3, "Needs review": 2, "In progress": 1}
	net_of_discount = cint(s.revenue_net_of_discounts)
	for r in revenue:
		ls = by_order.get(r.name) or (by_inv.get(r.sales_invoice) if r.sales_invoice else None)
		if not ls:
			continue
		best = max((status_of[l.status] for l in ls), key=lambda k: rank_[k])
		r.coll_state = best
		r.fee = sum(flt(l.delivery_fee) for l in ls)
		r.fee_actual = 1
		r.discount = sum(flt(l.discount) for l in ls)
		r.other_exp = sum(flt(l.other_expenses) for l in ls)
		if best == "Remitted":
			done = [l for l in ls if status_of[l.status] == "Remitted"]
			r.net_collected = sum(flt(l.collection_amount) for l in done)
			cd = min(getdate(l.collection_date) for l in done if l.collection_date)
			if r.actual_delivery_date:
				r.days_to_remit = max(date_diff(cd, r.actual_delivery_date), 0)
		if net_of_discount:
			r.rev_value = r.order_total - r.discount


# ---------------------------------------------------------------- enrichment

def status_lookup(s):
	return {r.crm_status: r.status_type for r in s.status_map}


def state_lookup(s):
	states = {norm(r.state): (r.state, r.zone) for r in s.states}
	zone_of = {r.state: r.zone for r in s.states}
	aliases = {norm(r.alias): r.state for r in s.state_aliases}

	def resolve(raw):
		n = norm(raw)
		if not n:
			return "Not captured", "Not captured"
		for key in (n, re.sub(r"\s+state$", "", n)):
			if key in states:
				return states[key]
			if key in aliases:
				st = aliases[key]
				return st, zone_of.get(st, "Unmapped")
		return clean(raw).title(), "Unmapped"

	return resolve


def stage_of(stype, dispatched):
	if stype == "Won":
		return "Delivered"
	if stype == "Reversed":
		return "Reversed after delivery"
	if stype == "Invalid":
		return "Duplicate (invalid)"
	if stype == "Transit":
		return "In transit with agent"
	if stype == "Lost":
		return "Failed after dispatch" if dispatched else "Lost before dispatch"
	return "Stalled with agent" if dispatched else "Open with closer"


def enrich(rows, s):
	smap = status_lookup(s)
	resolve_state = state_lookup(s)
	default_fee = flt(s.default_agent_fee)
	for r in rows:
		r.order_total = flt(r.order_total)
		r.stype = smap.get(r.status, "Open")
		r.dispatched = 1 if r.portal_agent else 0
		r.stage = stage_of(r.stype, r.dispatched)
		r.valid = 0 if r.stype == "Invalid" else 1
		r.won = 1 if r.stype == "Won" else 0
		r.state_clean, r.zone = resolve_state(r.state)
		# Follow-up closer takes the credit when the order went through the follow-up pool
		if r.followup_closer:
			r.credit_closer, r.credit_closer_label = r.followup_closer, clean(r.followup_closer_name) or r.followup_closer
		else:
			r.credit_closer = r.closer or UNASSIGNED
			r.credit_closer_label = clean(r.closer_name) or r.closer or UNASSIGNED
		r.marketer = r.digital_marketer or UNASSIGNED
		r.marketer_label = clean(r.marketer_name) or r.digital_marketer or UNASSIGNED
		r.agent = r.portal_agent or UNASSIGNED
		r.agent_label = clean(r.portal_agent_name) or r.portal_agent or UNASSIGNED
		r.fee = flt(r.agent_delivery_fee) or default_fee
		r.order_day = getdate(r.order_date) if r.order_date else None
		if r.actual_delivery_date:
			r.recog_date, r.missing_delivery_date = getdate(r.actual_delivery_date), 0
		else:
			fallback = r.last_updated_at or r.modified
			r.recog_date, r.missing_delivery_date = (getdate(fallback) if fallback else None), 1
	return rows


# ---------------------------------------------------------------- aggregation

def _blank(key, label):
	return frappe._dict(key=key, label=label, orders=0, valid=0, duplicates=0, dispatched=0, delivered=0,
		failed=0, lost_pre=0, reversed=0, open=0, stalled=0, transit=0, open_value=0, delivered_value=0,
		calls=0, revenue=0.0, deliveries=0, units=0, upsell_orders=0, upsell_value=0.0, cross_value=0.0,
		fees=0.0, days_sum=0, days_n=0, gross=0.0, discount=0.0, other_exp=0.0, net_collected=0.0, remitted=0,
		in_progress_value=0.0, review=0, outstanding=0, outstanding_value=0.0, fee_actual=0, remit_days_sum=0,
		remit_days_n=0, spend=0.0, attrs={})


def aggregate(cohort, revenue, key, label, attr=None):
	"""Group cohort and revenue rows by key(row). attr(row) -> value used to find the most common attribute."""
	groups = {}

	def g(r):
		k = key(r)
		if k not in groups:
			groups[k] = _blank(k, label(r))
		return groups[k]

	for r in cohort:
		x = g(r)
		x.orders += 1
		x.valid += r.valid
		x.duplicates += 1 - r.valid
		if r.valid and r.dispatched:
			x.dispatched += 1
		x.delivered += r.won
		x.delivered_value += r.order_total if r.won else 0
		st = r.stage
		if st == "Failed after dispatch":
			x.failed += 1
		elif st == "Lost before dispatch":
			x.lost_pre += 1
		elif st == "Reversed after delivery":
			x.reversed += 1
		elif st in OPEN_STAGES:
			x.open += 1
			x.open_value += r.order_total
			if st == "Stalled with agent":
				x.stalled += 1
			elif st == "In transit with agent":
				x.transit += 1
		if r.valid:
			x.calls += cint(r.call_attempts)
		if attr:
			a = attr(r)
			x.attrs[a] = x.attrs.get(a, 0) + 1
	for r in revenue:
		x = g(r)
		x.revenue += r.rev_value
		x.gross += r.order_total
		x.deliveries += 1
		x.discount += flt(r.discount)
		x.other_exp += flt(r.other_exp)
		x.net_collected += flt(r.net_collected)
		x.fee_actual += cint(r.fee_actual)
		if r.coll_state == "Remitted":
			x.remitted += 1
		elif r.coll_state == "In progress":
			x.in_progress_value += r.order_total
		elif r.coll_state == "Needs review":
			x.review += 1
		else:
			x.outstanding += 1
			x.outstanding_value += r.order_total
		if r.days_to_remit is not None:
			x.remit_days_sum += r.days_to_remit
			x.remit_days_n += 1
		x.units += flt(r.total_qty)
		x.upsell_orders += cint(r.has_upsell)
		x.upsell_value += flt(r.upsell_value)
		x.cross_value += flt(r.cross_sell_value)
		x.fees += r.fee
		if r.agent_assignment_date and r.actual_delivery_date:
			x.days_sum += max(date_diff(r.actual_delivery_date, r.agent_assignment_date), 0)
			x.days_n += 1
	total_rev = sum(r.rev_value for r in revenue)
	for x in groups.values():
		finish(x, total_rev)
	return list(groups.values())


def finish(x, total_rev):
	x.conversion = pct(x.delivered, x.valid)
	x.success = pct(x.delivered, x.dispatched)
	x.fail_rate = pct(x.failed, x.dispatched)
	x.dup_rate = pct(x.duplicates, x.orders)
	x.share = pct(x.revenue, total_rev)
	x.aov = x.revenue / x.deliveries if x.deliveries else 0
	x.upsell_attach = pct(x.upsell_orders, x.deliveries)
	x.calls_per_order = x.calls / x.valid if x.valid else 0
	x.avg_days = round(x.days_sum / x.days_n, 1) if x.days_n else None
	x.net_cash = x.gross - x.fees - x.discount - x.other_exp
	x.avg_remit_days = round(x.remit_days_sum / x.remit_days_n, 1) if x.remit_days_n else None
	x.fee_actual_pct = pct(x.fee_actual, x.deliveries)
	x.cpl = x.spend / x.valid if x.spend and x.valid else None
	x.cpa = x.spend / x.delivered if x.spend and x.delivered else None
	x.roas = x.delivered_value / x.spend if x.spend else None
	x.units_per_order = x.units / x.deliveries if x.deliveries else 0
	x.main_attr = max(x.attrs, key=x.attrs.get) if x.attrs else ""
	return x


def total_row(rows, total_rev, label="Total"):
	t = _blank(None, label)
	for x in rows:
		for f in ("orders", "valid", "duplicates", "dispatched", "delivered", "failed", "lost_pre", "reversed", "open",
			"stalled", "transit", "open_value", "delivered_value", "calls", "revenue", "deliveries", "units",
			"upsell_orders", "upsell_value", "cross_value", "fees", "days_sum", "days_n", "gross", "discount", "other_exp",
			"net_collected", "remitted", "in_progress_value", "review", "outstanding", "outstanding_value", "fee_actual",
			"remit_days_sum", "remit_days_n", "spend"):
			t[f] += x[f]
	finish(t, total_rev)
	t.rank = None
	t.bold = 1
	return t


def rank(rows, volume_field, threshold, metric):
	eligible = [x for x in rows if x[volume_field] >= threshold and x.key not in (UNASSIGNED, None, "")]
	ordered = sorted(eligible, key=lambda x: -x[metric])
	pos = {}
	for i, x in enumerate(ordered):
		if i and x[metric] == ordered[i - 1][metric]:
			pos[id(x)] = pos[id(ordered[i - 1])]
		else:
			pos[id(x)] = i + 1
	for x in rows:
		x.rank = pos.get(id(x))


def summary(cohort, revenue):
	valid = [r for r in cohort if r.valid]
	disp = [r for r in valid if r.dispatched]
	delivered = sum(r.won for r in cohort)
	rev = sum(r.rev_value for r in revenue)
	outstanding = sum(r.order_total for r in revenue if r.coll_state == "Not collected")
	open_value = sum(r.order_total for r in cohort if r.stage in OPEN_STAGES)
	failed = sum(1 for r in cohort if r.stage == "Failed after dispatch")
	delivered_value = sum(r.order_total for r in cohort if r.won)
	return frappe._dict(orders=len(cohort), delivered_value=delivered_value, valid=len(valid), dispatched=len(disp), delivered=delivered,
		conversion=pct(delivered, len(valid)), success=pct(delivered, len(disp)), fail_rate=pct(failed, len(disp)),
		failed=failed, open_value=open_value, revenue=rev, deliveries=len(revenue),
		aov=rev / len(revenue) if revenue else 0, outstanding=outstanding)


def kpis(s):
	return [
		{"value": s.revenue, "label": "Revenue recognised", "datatype": "Currency", "indicator": "Green"},
		{"value": s.deliveries, "label": "Deliveries", "datatype": "Int", "indicator": "Green"},
		{"value": s.conversion, "label": "Conversion (delivered ÷ valid)", "datatype": "Percent", "indicator": "Blue"},
		{"value": s.success, "label": "Delivery success", "datatype": "Percent", "indicator": "Blue"},
		{"value": s.fail_rate, "label": "Failed after dispatch", "datatype": "Percent", "indicator": "Red"},
		{"value": s.open_value, "label": "Open pipeline value", "datatype": "Currency", "indicator": "Orange"},
	]


def col(label, fieldname, fieldtype="Data", width=110, options=None):
	c = {"label": label, "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
	if options:
		c["options"] = options
	return c


# ---------------------------------------------------------------- marketing spend

def mkey(x):
	return (x or "").strip().lower()


def pkey(x):
	return re.sub(r"\s+", " ", (x or "").strip()).upper()


def fetch_spend(from_date, to_date):
	"""Marketing Spend entries in the period (spend has no company or branch)."""
	if not frappe.db.exists("DocType", "Marketing Spend"):
		return []
	return frappe.db.sql(
		"""select spend_date, digital_marketer, product_category, platform, campaign_title, amount_spent
		from `tabMarketing Spend` where spend_date between %(fd)s and %(td)s""",
		{"fd": getdate(from_date), "td": getdate(to_date)}, as_dict=True)


def spend_note(f):
	notes = []
	if f.get("branch"):
		notes.append("Ad spend is not recorded by branch, so spend and ROAS are hidden when a Branch filter is set.")
	if frappe.db.sql("select count(distinct company) from `tabCRM Order` where company is not null")[0][0] > 1:
		notes.append("Marketing Spend has no company field: spend shown is for all companies on this site.")
	return " ".join(notes)


def marketer_name(email):
	return frappe.db.get_value("User", email, "full_name") or email


def spend_kpis(cohort, spend):
	total = sum(flt(x.amount_spent) for x in spend)
	valid = sum(r.valid for r in cohort)
	delivered = sum(r.won for r in cohort)
	dv = sum(r.order_total for r in cohort if r.won)
	return [
		{"value": total, "label": "Ad spend", "datatype": "Currency", "indicator": "Orange"},
		{"value": total / valid if valid else 0, "label": "Cost per valid lead", "datatype": "Currency", "indicator": "Blue"},
		{"value": total / delivered if delivered else 0, "label": "Cost per delivered order", "datatype": "Currency", "indicator": "Blue"},
		{"value": dv / total if total else 0, "label": "ROAS (delivered value ÷ spend)", "datatype": "Float", "indicator": "Green"},
	]
