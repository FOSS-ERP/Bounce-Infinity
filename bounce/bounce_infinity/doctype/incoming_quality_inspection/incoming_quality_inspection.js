frappe.ui.form.on("Incoming QC Allocation", {
	accepted_qty: calculate_totals,
	rejected_qty: calculate_totals,
});

frappe.ui.form.on("Incoming Quality Inspection", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && (frm.doc.allocations || []).length) {
			frm.add_custom_button(__("Allocate Total QC Result"), () =>
				open_allocation_dialog(frm)
			);
		}
	},
});

function open_allocation_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Allocate Total QC Result"),
		fields: [
			{
				fieldname: "accepted_qty",
				fieldtype: "Float",
				label: __("Accepted Quantity"),
				reqd: 1,
			},
			{
				fieldname: "rejected_qty",
				fieldtype: "Float",
				label: __("Rejected Quantity"),
				reqd: 1,
			},
			{
				fieldname: "rejection_reason",
				fieldtype: "Small Text",
				label: __("Rejection Reason"),
			},
		],
		primary_action_label: __("Allocate Oldest GRN First"),
		primary_action(values) {
			const accepted = flt(values.accepted_qty);
			const rejected = flt(values.rejected_qty);
			if (
				accepted < 0 ||
				rejected < 0 ||
				accepted + rejected > flt(frm.doc.total_pending_qty)
			) {
				frappe.msgprint(
					__("The QC result must be between zero and total pending quantity {0}.", [
						frm.doc.total_pending_qty,
					])
				);
				return;
			}
			if (rejected && !values.rejection_reason) {
				frappe.msgprint(__("Rejection Reason is required."));
				return;
			}
			distribute_quantities(frm, accepted, rejected);
			frm.set_value("rejection_reason", values.rejection_reason || "");
			dialog.hide();
		},
	});
	dialog.show();
}

function distribute_quantities(frm, accepted_qty, rejected_qty) {
	let accepted_remaining = accepted_qty;
	let rejected_remaining = rejected_qty;
	(frm.doc.allocations || []).forEach((row) => {
		const pending = flt(row.pending_qty);
		row.accepted_qty = Math.min(pending, accepted_remaining);
		accepted_remaining -= row.accepted_qty;
		const capacity = pending - row.accepted_qty;
		row.rejected_qty = Math.min(capacity, rejected_remaining);
		rejected_remaining -= row.rejected_qty;
		row.remaining_qty = pending - row.accepted_qty - row.rejected_qty;
	});
	frm.refresh_field("allocations");
	frm.set_value("total_accepted_qty", accepted_qty);
	frm.set_value("total_rejected_qty", rejected_qty);
	frm.set_value(
		"total_remaining_qty",
		flt(frm.doc.total_pending_qty) - accepted_qty - rejected_qty
	);
}

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
