frappe.query_reports["Distribution Efficiency"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "view_by", label: __("View By"), fieldtype: "Select", reqd: 1, default: "Location", options: ["Location", "Zone"] },
		{ fieldname: "location_type", label: __("Location Type"), fieldtype: "Select", default: "Agent", options: ["", "HQ", "Agent", "Transit", "Other"] },
		{ fieldname: "zone", label: __("Zone"), fieldtype: "Select", options: ["", "North Central", "North East", "North West", "South East", "South South", "South West", "Not captured"] },
		{ fieldname: "warehouse", label: __("Location"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "status" && data.status) {
			const c = { "Stock-out": "red", "Understocked": "orange", "Healthy": "green", "Overstocked": "yellow", "Idle": "gray", "Slow": "gray" }[data.status];
			if (c) value = `<span class="indicator-pill ${c}">${value}</span>`;
		}
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
