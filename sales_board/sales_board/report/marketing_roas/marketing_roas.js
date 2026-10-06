frappe.query_reports["Marketing ROAS"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "view_by", label: __("View By"), fieldtype: "Select", reqd: 1, default: "Marketer × Product", options: ["Marketer × Product", "Product", "Marketer"] },
		{ fieldname: "live", label: __("Live data (ignore month-end snapshot)"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "roas" && data.roas !== null && data.roas !== undefined && !data.bold) {
			const c = data.roas >= 3 ? "green" : data.roas >= 1.5 ? "orange" : "red";
			value = `<span style="color:var(--${c}-600);font-weight:600">${value}</span>`;
		}
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
