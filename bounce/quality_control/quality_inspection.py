import frappe
from frappe import _
from frappe.utils import flt


def validate_qc_allocations(doc, method=None):
	"""Validate the quantities entered in the QC allocation table."""
	if not doc.get("custom_qc_receipts"):
		return

	if not doc.get("custom_qc_item"):
		frappe.throw(_("Select an Item before adding GRNs for QC."))
	doc.item_code = doc.custom_qc_item

	seen_rows = set()
	for allocation in doc.custom_qc_receipts:
		_validate_allocation_row(doc, allocation, seen_rows)


def validate_qc_allocations_for_submit(doc, method=None):
	"""Recheck submitted allocations while locking their Purchase Receipt rows."""
	validate_qc_allocations(doc)
	if not doc.get("custom_qc_receipts"):
		return

	for allocation in doc.custom_qc_receipts:
		purchase_receipt_item = frappe.db.sql(
			"""
			SELECT name, parent, item_code, received_qty, qty
			FROM `tabPurchase Receipt Item`
			WHERE name = %s
			FOR UPDATE
			""",
			allocation.purchase_receipt_item,
			as_dict=True,
		)
		if not purchase_receipt_item:
			frappe.throw(
				_("Purchase Receipt row {0} no longer exists.").format(allocation.purchase_receipt_item)
			)

		pr_item = purchase_receipt_item[0]
		pending_qty = _get_pending_qty(pr_item, exclude_quality_inspection=doc.name)
		allocated_qty = flt(allocation.accepted_qty) + flt(allocation.rejected_qty)
		if allocated_qty > pending_qty:
			frappe.throw(
				_("Row {0}: only {1} is pending QC for Purchase Receipt {2}, but {3} was allocated.").format(
					allocation.idx, pending_qty, allocation.purchase_receipt, allocated_qty
				)
			)
		if flt(allocation.rejected_qty) and not allocation.rejection_reason:
			frappe.throw(
				_("Row {0}: Rejection Reason is required for rejected quantity.").format(allocation.idx)
			)


def process_qc_result(doc, method=None):
	"""Move inspected stock and refresh QC status on every affected Purchase Receipt."""
	if not doc.get("custom_qc_receipts"):
		return

	settings = frappe.get_single("Bounce QC Settings")
	accepted_rows = _aggregate_transfer_rows(doc.custom_qc_receipts, "accepted_qty")
	rejected_rows = _aggregate_transfer_rows(doc.custom_qc_receipts, "rejected_qty")

	accepted_entry = _create_stock_entry(doc, accepted_rows, settings.accepted_warehouse, _("Accepted"))
	rejected_entry = _create_stock_entry(doc, rejected_rows, settings.rejected_warehouse, _("Rejected"))

	if accepted_entry:
		doc.db_set("custom_accepted_stock_entry", accepted_entry, update_modified=False)
	if rejected_entry:
		doc.db_set("custom_rejected_stock_entry", rejected_entry, update_modified=False)

	_update_purchase_receipt_qc_statuses(doc.custom_qc_receipts)


def reverse_qc_result(doc, method=None):
	"""Cancel automatic transfers and reopen quantities when an inspection is cancelled."""
	for fieldname in ("custom_accepted_stock_entry", "custom_rejected_stock_entry"):
		stock_entry = doc.get(fieldname)
		if stock_entry and frappe.db.get_value("Stock Entry", stock_entry, "docstatus") == 1:
			frappe.get_doc("Stock Entry", stock_entry).cancel()

	_update_purchase_receipt_qc_statuses(doc.get("custom_qc_receipts") or [])


@frappe.whitelist()
def get_pending_qc_receipts(item_code: str):
	if not item_code:
		frappe.throw(_("Item is required."))
	if not frappe.has_permission("Quality Inspection", "create"):
		frappe.throw(_("You are not permitted to create Quality Inspections."), frappe.PermissionError)
	if not frappe.has_permission("Purchase Receipt", "read"):
		frappe.throw(_("You are not permitted to read Purchase Receipts."), frappe.PermissionError)

	rows = frappe.db.sql(
		"""
		SELECT
			pri.name AS purchase_receipt_item,
			pri.parent AS purchase_receipt,
			pri.item_code,
			pri.warehouse AS source_warehouse,
			pr.posting_date,
			COALESCE(NULLIF(pri.received_qty, 0), pri.qty, 0) AS received_qty
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1 AND pr.is_return = 0 AND pri.item_code = %s
		ORDER BY pr.posting_date, pr.posting_time, pr.name, pri.idx
		""",
		item_code,
		as_dict=True,
	)

	result = []
	purchase_receipt_permissions = {}
	for row in rows:
		if row.purchase_receipt not in purchase_receipt_permissions:
			purchase_receipt_permissions[row.purchase_receipt] = frappe.has_permission(
				"Purchase Receipt", "read", row.purchase_receipt
			)
		if not purchase_receipt_permissions[row.purchase_receipt]:
			continue

		inspected_qty = _get_inspected_qty(row.purchase_receipt_item)
		pending_qty = max(flt(row.received_qty) - inspected_qty, 0)
		if pending_qty:
			result.append(
				{
					**row,
					"inspected_qty": inspected_qty,
					"pending_qty": pending_qty,
				}
			)

	return result


def _validate_allocation_row(doc, allocation, seen_rows):
	if not allocation.purchase_receipt_item:
		frappe.throw(_("Row {0}: Purchase Receipt Item is required.").format(allocation.idx))
	if allocation.purchase_receipt_item in seen_rows:
		frappe.throw(
			_("Row {0}: the same Purchase Receipt row cannot be allocated twice.").format(allocation.idx)
		)
	seen_rows.add(allocation.purchase_receipt_item)

	pr_item = frappe.db.get_value(
		"Purchase Receipt Item",
		allocation.purchase_receipt_item,
		["name", "parent", "item_code", "warehouse", "docstatus", "received_qty", "qty"],
		as_dict=True,
	)
	if not pr_item or pr_item.docstatus != 1:
		frappe.throw(_("Row {0}: Purchase Receipt must be submitted.").format(allocation.idx))
	if pr_item.parent != allocation.purchase_receipt or pr_item.item_code != doc.custom_qc_item:
		frappe.throw(
			_("Row {0}: Purchase Receipt row does not match the selected Item.").format(allocation.idx)
		)
	if not pr_item.warehouse:
		frappe.throw(_("Row {0}: the Purchase Receipt row has no Quality Warehouse.").format(allocation.idx))
	if allocation.source_warehouse and allocation.source_warehouse != pr_item.warehouse:
		frappe.throw(
			_("Row {0}: the Quality Warehouse does not match the Purchase Receipt.").format(allocation.idx)
		)

	accepted_qty = flt(allocation.accepted_qty)
	rejected_qty = flt(allocation.rejected_qty)
	if accepted_qty < 0 or rejected_qty < 0:
		frappe.throw(
			_("Row {0}: accepted and rejected quantities cannot be negative.").format(allocation.idx)
		)
	if doc.get("_action") == "submit" and accepted_qty + rejected_qty <= 0:
		frappe.throw(
			_("Row {0}: enter an accepted or rejected quantity before submitting.").format(allocation.idx)
		)

	received_qty = flt(pr_item.received_qty) or flt(pr_item.qty)
	inspected_qty = _get_inspected_qty(pr_item.name, doc.name)
	pending_qty = max(received_qty - inspected_qty, 0)
	if accepted_qty + rejected_qty > pending_qty:
		frappe.throw(
			_("Row {0}: accepted plus rejected quantity cannot exceed pending QC quantity ({1}).").format(
				allocation.idx, pending_qty
			)
		)

	allocation.item_code = pr_item.item_code
	allocation.source_warehouse = pr_item.warehouse
	allocation.received_qty = received_qty
	allocation.already_inspected_qty = inspected_qty
	allocation.pending_qty = pending_qty
	allocation.remaining_qty = pending_qty - accepted_qty - rejected_qty


def _get_inspected_qty(purchase_receipt_item, exclude_quality_inspection=None):
	if exclude_quality_inspection:
		query = """
			SELECT COALESCE(SUM(qci.accepted_qty + qci.rejected_qty), 0)
			FROM `tabQuality Inspection PR Detail` qci
			INNER JOIN `tabQuality Inspection` qi ON qi.name = qci.parent
			WHERE qci.purchase_receipt_item = %s
				AND qi.docstatus = 1
				AND qi.name != %s
		"""
		values = (purchase_receipt_item, exclude_quality_inspection)
	else:
		query = """
			SELECT COALESCE(SUM(qci.accepted_qty + qci.rejected_qty), 0)
			FROM `tabQuality Inspection PR Detail` qci
			INNER JOIN `tabQuality Inspection` qi ON qi.name = qci.parent
			WHERE qci.purchase_receipt_item = %s
				AND qi.docstatus = 1
		"""
		values = (purchase_receipt_item,)

	return flt(frappe.db.sql(query, values)[0][0])


def _get_pending_qty(pr_item, exclude_quality_inspection=None):
	received_qty = flt(pr_item.received_qty) or flt(pr_item.qty)
	return max(received_qty - _get_inspected_qty(pr_item.name, exclude_quality_inspection), 0)


def _aggregate_transfer_rows(allocations, quantity_field):
	rows = {}
	for allocation in allocations:
		qty = flt(allocation.get(quantity_field))
		if not qty:
			continue
		key = (allocation.get("item_code"), allocation.get("source_warehouse"))
		rows[key] = rows.get(key, 0) + qty
	return rows


def _create_stock_entry(quality_inspection, rows, target_warehouse, result_label):
	if not rows:
		return None
	if not target_warehouse:
		frappe.throw(_("Set the {0} Material Warehouse in Bounce QC Settings.").format(result_label))

	companies = {
		frappe.db.get_value("Purchase Receipt", row.purchase_receipt, "company")
		for row in quality_inspection.custom_qc_receipts
	}
	if len(companies) != 1:
		frappe.throw(_("One Quality Inspection cannot allocate Purchase Receipts from different companies."))

	stock_entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": companies.pop(),
			"remarks": _("Automatic {0} QC transfer for Quality Inspection {1}").format(
				result_label, quality_inspection.name
			),
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"s_warehouse": source_warehouse,
					"t_warehouse": target_warehouse,
				}
				for (item_code, source_warehouse), qty in rows.items()
			],
		}
	)
	stock_entry.insert()
	stock_entry.submit()
	return stock_entry.name


def _update_purchase_receipt_qc_statuses(allocations):
	for purchase_receipt in {row.purchase_receipt for row in allocations if row.purchase_receipt}:
		totals = frappe.db.sql(
			"""
			SELECT
				COALESCE(SUM(COALESCE(NULLIF(pri.received_qty, 0), pri.qty, 0)), 0) AS received_qty,
				COALESCE(SUM(inspected.inspected_qty), 0) AS inspected_qty
			FROM `tabPurchase Receipt Item` pri
			LEFT JOIN (
				SELECT qci.purchase_receipt_item,
					SUM(qci.accepted_qty + qci.rejected_qty) AS inspected_qty
				FROM `tabQuality Inspection PR Detail` qci
				INNER JOIN `tabQuality Inspection` qi ON qi.name = qci.parent
				WHERE qi.docstatus = 1
				GROUP BY qci.purchase_receipt_item
			) inspected ON inspected.purchase_receipt_item = pri.name
			WHERE pri.parent = %s
			""",
			(purchase_receipt,),
			as_dict=True,
		)[0]

		if not flt(totals.inspected_qty):
			status = "QC Pending"
		elif flt(totals.inspected_qty) < flt(totals.received_qty):
			status = "Partial QC Done"
		else:
			status = "QC Completed"

		frappe.db.set_value("Purchase Receipt", purchase_receipt, "custom_qc_status", status)
