frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frappe.call({
			method: "bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection.get_purchase_receipt_inspections",
			args: { purchase_receipt: frm.doc.name },
			callback(response) {
				const inspections = response.message || [];
				if (!inspections.length) {
					return;
				}
				const links = inspections
					.map(
						(inspection) => `<div class="mb-2">
							<a href="/app/incoming-quality-inspection/${encodeURIComponent(inspection.name)}">
								${frappe.utils.escape_html(inspection.name)}
							</a>
							<span class="text-muted ml-2">${frappe.utils.escape_html(inspection.item_code || "")} · ${__(
							inspection.status
						)}</span>
						</div>`
					)
					.join("");
				frm.dashboard.add_section(
					links,
					__("Incoming Quality Inspections"),
					"incoming-quality-inspection-connections"
				);
				if (
					frm.doc.docstatus === 1 &&
					!frm.doc.is_return &&
					inspections.some(
						(inspection) =>
							inspection.docstatus === 1 && flt(inspection.total_rejected_qty) > 0
					)
				) {
					frm.add_custom_button(
						__("QC Purchase Return"),
						() => create_qc_purchase_return(frm),
						__("Create")
					);
				}
			},
		});
	},
});

async function create_qc_purchase_return(frm) {
	const response = await frappe.call({
		method: "bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection.create_qc_purchase_returns_for_receipt",
		args: { purchase_receipt: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating QC Purchase Return..."),
	});
	const returns = response.message || [];
	if (!returns.length) {
		frappe.msgprint(__("All rejected quantities have already been returned."));
	} else if (returns.length === 1) {
		frappe.set_route("Form", "Purchase Receipt", returns[0]);
	} else {
		frappe.msgprint(__("Created Purchase Returns: {0}", [returns.join(", ")]));
	}
}
