frappe.ui.form.on("Warranty Claim", {
	async serial_no(frm) {
		if (!frm.doc.serial_no) return;
		const serial = await frappe.db.get_doc("Serial No", frm.doc.serial_no);
		for (const field of [
			"custom_supplier",
			"custom_original_purchase_receipt",
			"custom_original_purchase_rate",
			"custom_purchase_return",
			"custom_supplier_debit_note",
		]) {
			await frm.set_value(field, serial[field]);
		}
		await frm.set_value("custom_supplier_claim_multiplier", serial.custom_supplier_claim_multiplier || 2);
		await frm.set_value(
			"custom_supplier_claim_amount",
			flt(serial.custom_original_purchase_rate) * flt(serial.custom_supplier_claim_multiplier || 2)
		);
	},
	refresh(frm) {
		if (!frm.doc.serial_no || frm.is_new()) return;
		frm.add_custom_button(__("Supplier Warranty Return"), () => create_from_claim(frm, "create_supplier_return", "Purchase Receipt"), __("Create"));
		frm.add_custom_button(__("Warranty Debit Note"), () => create_from_claim(frm, "create_warranty_debit_note", "Purchase Invoice"), __("Create"));
	},
});

async function create_from_claim(frm, action, doctype) {
	const response = await frappe.call({
		method: `bounce.supplier_warranty.${action}`,
		args: { serial_no: frm.doc.serial_no, warranty_claim: frm.doc.name },
		freeze: true,
	});
	frappe.set_route("Form", doctype, response.message);
}
