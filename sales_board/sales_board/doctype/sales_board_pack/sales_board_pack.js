frappe.ui.form.on("Sales Board Pack", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Rebuild pack"), () =>
			frm.call("regenerate").then(() => { frm.reload_doc(); frappe.show_alert(__("Pack rebuilt")); }));
		frm.add_custom_button(frm.doc.status === "Sent" ? __("Send again") : __("Send to management"), () => {
			const go = () => frm.call("send_to_management").then((r) => {
				frm.reload_doc();
				frappe.msgprint(__("Sent to {0}", [r.message]));
			});
			if (frm.is_dirty()) frm.save().then(go); else go();
		}).addClass("btn-primary");
	},
});
