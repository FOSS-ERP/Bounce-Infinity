frappe.ui.form.on("Incoming QC Allocation", {
	accepted_qty: calculate_totals,
	rejected_qty: calculate_totals,
});

frappe.ui.form.on("Incoming Quality Inspection", {
	setup(frm) {
		frm.set_query("accepted_warehouse", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
				custom_is_qc_accepted_warehouse: 1,
			},
		}));
		frm.set_query("rejected_warehouse", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
				custom_is_qc_rejected_warehouse: 1,
			},
		}));
	},
});

function calculate_totals(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const accepted = flt(row.accepted_qty);
	const rejected = flt(row.rejected_qty);
	if (accepted + rejected > flt(row.pending_qty)) {
		frappe.model.set_value(cdt, cdn, "accepted_qty", 0);
		frappe.model.set_value(cdt, cdn, "rejected_qty", 0);
		frappe.msgprint(
			__("Accepted plus rejected cannot exceed pending quantity {0}.", [row.pending_qty])
		);
		return;
	}
	frappe.model.set_value(cdt, cdn, "remaining_qty", flt(row.pending_qty) - accepted - rejected);
	const totals = (frm.doc.allocations || []).reduce(
		(result, allocation) => {
			result.pending += flt(allocation.pending_qty);
			result.accepted += flt(allocation.accepted_qty);
			result.rejected += flt(allocation.rejected_qty);
			result.remaining += flt(allocation.remaining_qty);
			return result;
		},
		{ pending: 0, accepted: 0, rejected: 0, remaining: 0 }
	);
	frm.set_value("total_pending_qty", totals.pending);
	frm.set_value("total_accepted_qty", totals.accepted);
	frm.set_value("total_rejected_qty", totals.rejected);
	frm.set_value("total_remaining_qty", totals.remaining);
}
