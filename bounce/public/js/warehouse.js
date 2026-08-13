frappe.ui.form.on("Warehouse", {
	setup(frm) {
		frm.set_query("custom_qc_accepted_warehouse", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
				custom_is_qc_accepted_warehouse: 1,
			},
		}));
		frm.set_query("custom_qc_rejected_warehouse", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
				custom_is_qc_rejected_warehouse: 1,
			},
		}));
	},
});
