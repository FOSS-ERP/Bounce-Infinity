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
							<span class="text-muted ml-2">${frappe.utils.escape_html(
								inspection.item_code || ""
							)} · ${__(inspection.status)}</span>
						</div>`
					)
					.join("");
				frm.dashboard.add_section(
					links,
					__("Incoming Quality Inspections"),
					"incoming-quality-inspection-connections"
				);
			},
		});
	},
});
