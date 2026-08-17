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
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Revise QC Result"), () => show_qc_revision_dialog(frm));
		}
		if (frm.doc.docstatus === 1 && flt(frm.doc.total_rejected_qty) > 0) {
			frm.add_custom_button(
				__("Create Purchase Return"),
				async () => {
					const response = await frappe.call({
						method: "bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection.create_qc_purchase_returns",
						args: { inspection: frm.doc.name },
						freeze: true,
						freeze_message: __("Creating Purchase Return..."),
					});
					const returns = response.message || [];
					if (!returns.length) {
						frappe.msgprint(__("All rejected quantities have already been returned."));
					} else if (returns.length === 1) {
						frappe.set_route("Form", "Purchase Receipt", returns[0]);
					} else {
						frappe.msgprint(__("Created Purchase Returns: {0}", [returns.join(", ")]));
					}
				},
				__("Create")
			);
		}
	},
});

function show_qc_revision_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Revise QC Result"),
		fields: [
			{
				fieldname: "allocations",
				fieldtype: "Table",
				label: __("Revised Quantities"),
				cannot_add_rows: true,
				cannot_delete_rows: true,
				in_place_edit: true,
				data: (frm.doc.allocations || []).map((row) => ({
					allocation: row.name,
					item_code: row.item_code,
					purchase_receipt: row.purchase_receipt,
					accepted_qty: row.accepted_qty,
					rejected_qty: row.rejected_qty,
				})),
				fields: [
					{ fieldname: "allocation", fieldtype: "Data", hidden: 1 },
					{
						fieldname: "item_code",
						fieldtype: "Link",
						options: "Item",
						label: __("Item"),
						in_list_view: true,
						read_only: true,
						columns: 2,
					},
					{
						fieldname: "purchase_receipt",
						fieldtype: "Link",
						options: "Purchase Receipt",
						label: __("Purchase Receipt"),
						in_list_view: true,
						read_only: true,
						columns: 2,
					},
					{
						fieldname: "accepted_qty",
						fieldtype: "Float",
						label: __("Revised Accepted Qty"),
						in_list_view: true,
						columns: 2,
					},
					{
						fieldname: "rejected_qty",
						fieldtype: "Float",
						label: __("Revised Rejected Qty"),
						in_list_view: true,
						columns: 2,
					},
				],
			},
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Revision Reason"),
				reqd: true,
			},
		],
		primary_action_label: __("Revise and Transfer Stock"),
		async primary_action(values) {
			const response = await frappe.call({
				method: "bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection.revise_qc_result",
				args: {
					inspection: frm.doc.name,
					allocations: values.allocations,
					reason: values.reason,
				},
				freeze: true,
				freeze_message: __("Revising QC result and transferring stock..."),
			});
			dialog.hide();
			await frm.reload_doc();
			const entries = response.message?.stock_entries || [];
			frappe.msgprint(
				entries.length
					? __("QC result revised. Corrective Stock Entries: {0}", [entries.join(", ")])
					: __("QC result revised.")
			);
		},
	});
	dialog.show();
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
