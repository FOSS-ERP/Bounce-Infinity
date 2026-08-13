frappe.ui.form.on("Quality Inspection", {
	refresh(frm) {
		if (!frm.is_new() || !frm.doc.custom_qc_item || frm.doc.docstatus !== 0) {
			return;
		}

		frm.add_custom_button(__("Get GRN for QC"), () => get_grn_for_qc(frm));
	},

	custom_qc_item(frm) {
		frm.set_value("item_code", frm.doc.custom_qc_item);
		frm.clear_table("custom_qc_receipts");
		frm.refresh_field("custom_qc_receipts");
	},
});

frappe.ui.form.on("Quality Inspection PR Detail", {
	accepted_qty: calculate_remaining_qty,
	rejected_qty: calculate_remaining_qty,
});

async function get_grn_for_qc(frm) {
	if (!frm.doc.custom_qc_item) {
		frappe.msgprint(__("Please select an Item first."));
		return;
	}

	frappe.dom.freeze(__("Fetching Purchase Receipts pending QC..."));
	try {
		const response = await frappe.call({
			method: "bounce.quality_control.quality_inspection.get_pending_qc_receipts",
			args: {
				item_code: frm.doc.custom_qc_item,
			},
		});
		const rows = response.message || [];
		frm.clear_table("custom_qc_receipts");
		rows.forEach((source) => {
			const row = frm.add_child("custom_qc_receipts");
			Object.assign(row, {
				purchase_receipt: source.purchase_receipt,
				purchase_receipt_item: source.purchase_receipt_item,
				item_code: source.item_code,
				received_qty: flt(source.received_qty),
				already_inspected_qty: flt(source.inspected_qty),
				pending_qty: flt(source.pending_qty),
				accepted_qty: 0,
				rejected_qty: 0,
				remaining_qty: flt(source.pending_qty),
			});
		});
		frm.refresh_field("custom_qc_receipts");

		if (!rows.length) {
			frappe.msgprint(__("No Purchase Receipt is pending QC for {0}.", [frm.doc.custom_qc_item]));
		} else {
			frappe.show_alert({
				message: __("{0} Purchase Receipt row(s) pending QC found", [rows.length]),
				indicator: "green",
			});
		}
	} finally {
		frappe.dom.unfreeze();
	}
}

function calculate_remaining_qty(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const inspected_qty = flt(row.accepted_qty) + flt(row.rejected_qty);
	if (inspected_qty > flt(row.pending_qty)) {
		frappe.model.set_value(cdt, cdn, "accepted_qty", 0);
		frappe.model.set_value(cdt, cdn, "rejected_qty", 0);
		frappe.model.set_value(cdt, cdn, "remaining_qty", flt(row.pending_qty));
		frappe.msgprint(__("Accepted + Rejected quantity cannot exceed Pending QC Qty ({0}).", [row.pending_qty]));
		return;
	}
	frappe.model.set_value(cdt, cdn, "remaining_qty", flt(row.pending_qty) - inspected_qty);
}
