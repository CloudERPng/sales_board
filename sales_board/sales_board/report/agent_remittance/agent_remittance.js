frappe.query_reports["Agent Remittance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("Delivered From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -60), reqd: 1 },
		{ fieldname: "to_date", label: __("Delivered To"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "show_orders", label: __("List unremitted orders"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
