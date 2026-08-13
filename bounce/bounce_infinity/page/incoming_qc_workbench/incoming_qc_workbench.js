frappe.pages["incoming-qc-workbench"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Incoming QC Workbench"),
		single_column: true,
	});
	const state = { rows: [] };

	const filters = {
		item_code: page.add_field({ label: __("Item"), fieldtype: "Link", options: "Item" }),
		purchase_receipt: page.add_field({
			label: __("Purchase Receipt"),
			fieldtype: "Link",
			options: "Purchase Receipt",
		}),
		supplier: page.add_field({
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		}),
		from_date: page.add_field({ label: __("Received From"), fieldtype: "Date" }),
		to_date: page.add_field({ label: __("Received To"), fieldtype: "Date" }),
	};

	page.set_primary_action(__("Create Incoming QC"), () => create_incoming_qc(state.rows));
	page.add_inner_button(__("Refresh"), () => load_rows());
	Object.values(filters).forEach((field) => {
		field.$input.on("change", () => load_rows());
	});

	const $content = $('<div class="incoming-qc-workbench mt-4"></div>').appendTo(page.main);

	async function load_rows() {
		const response = await frappe.call({
			method: "bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection.get_pending_qc_rows",
			args: Object.fromEntries(
				Object.entries(filters).map(([key, field]) => [key, field.get_value()])
			),
			freeze: true,
			freeze_message: __("Loading pending QC items..."),
		});
		state.rows = response.message || [];
		render_rows($content, state.rows);
	}

	load_rows();
};

function render_rows($content, rows) {
	if (!rows.length) {
		$content.html(
			`<div class="text-muted text-center p-5">${__("No items are pending QC.")}</div>`
		);
		return;
	}
	const body = rows
		.map(
			(row, index) => `<tr>
				<td><input type="checkbox" class="qc-row" data-index="${index}"></td>
				<td>${frappe.utils.escape_html(row.item_code)}</td>
				<td><a href="/app/purchase-receipt/${encodeURIComponent(
					row.purchase_receipt
				)}">${frappe.utils.escape_html(row.purchase_receipt)}</a></td>
				<td>${frappe.utils.escape_html(row.supplier || "")}</td>
				<td>${frappe.datetime.str_to_user(row.posting_date)}</td>
				<td>${frappe.utils.escape_html(row.source_warehouse)}</td>
				<td class="text-right">${format_number(row.received_qty)}</td>
				<td class="text-right">${format_number(row.inspected_qty)}</td>
				<td class="text-right">${format_number(row.pending_qty)}</td>
				<td>${__(row.qc_status)}</td>
			</tr>`
		)
		.join("");
	$content.html(`<div class="frappe-card p-3"><div class="table-responsive"><table class="table table-bordered">
		<thead><tr><th></th><th>${__("Item")}</th><th>${__("Purchase Receipt")}</th><th>${__(
		"Supplier"
	)}</th><th>${__("Received On")}</th><th>${__("Quality Warehouse")}</th><th>${__(
		"Received"
	)}</th><th>${__("Inspected")}</th><th>${__("Pending")}</th><th>${__(
		"QC Status"
	)}</th></tr></thead>
		<tbody>${body}</tbody></table></div></div>`);
	$content.data("rows", rows);
}

function create_incoming_qc(rows) {
	const selected = $(".incoming-qc-workbench .qc-row:checked")
		.map((_, checkbox) => rows[$(checkbox).data("index")])
		.get();
	if (!selected.length) {
		frappe.msgprint(__("Select at least one pending Purchase Receipt row."));
		return;
	}
	if (new Set(selected.map((row) => row.item_code)).size !== 1) {
		frappe.msgprint(__("Select rows for one Item at a time."));
		return;
	}
	if (new Set(selected.map((row) => row.company)).size !== 1) {
		frappe.msgprint(__("Selected rows must belong to the same Company."));
		return;
	}
	frappe.new_doc(
		"Incoming Quality Inspection",
		{ company: selected[0].company, item_code: selected[0].item_code },
		(doc) => {
			const total_pending = selected.reduce(
				(total, source) => total + flt(source.pending_qty),
				0
			);
			doc.total_pending_qty = total_pending;
			doc.total_remaining_qty = total_pending;
			selected.forEach((source) => {
				const row = frappe.model.add_child(doc, "Incoming QC Allocation", "allocations");
				Object.assign(row, {
					purchase_receipt: source.purchase_receipt,
					purchase_receipt_item: source.purchase_receipt_item,
					posting_date: source.posting_date,
					supplier: source.supplier,
					item_code: source.item_code,
					source_warehouse: source.source_warehouse,
					received_qty: source.received_qty,
					already_inspected_qty: source.inspected_qty,
					pending_qty: source.pending_qty,
					remaining_qty: source.pending_qty,
				});
			});
		}
	);
}
