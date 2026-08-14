frappe.ui.form.on("Serial No", {
	refresh(frm) {
		if (!frm.doc.custom_original_purchase_receipt) return;
		frm.add_custom_button(
			__("Open Original Purchase Receipt"),
			() =>
				frappe.set_route(
					"Form",
					"Purchase Receipt",
					frm.doc.custom_original_purchase_receipt
				),
			__("Actions")
		);
		frm.add_custom_button(
			__("Supplier Warranty Return"),
			() => create_supplier_document(frm, "create_supplier_return", "Purchase Receipt"),
			__("Create")
		);
		frm.add_custom_button(
			__("Warranty Debit Note"),
			() => create_supplier_document(frm, "create_warranty_debit_note", "Purchase Invoice"),
			__("Create")
		);
	},
	custom_supplier_claim_multiplier(frm) {
		frm.set_value(
			"custom_supplier_claim_amount",
			flt(frm.doc.custom_original_purchase_rate) *
				flt(frm.doc.custom_supplier_claim_multiplier)
		);
	},
});

async function create_supplier_document(frm, action, doctype) {
	const response = await frappe.call({
		method: `bounce.supplier_warranty.${action}`,
		args: { serial_no: frm.doc.name },
		freeze: true,
	});
	frappe.set_route("Form", doctype, response.message);
}
