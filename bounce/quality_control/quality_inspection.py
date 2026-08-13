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


@frappe.whitelist()
def get_pending_qc_receipts(item_code):
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
			COALESCE(NULLIF(pri.received_qty, 0), pri.qty, 0) AS received_qty
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1 AND pri.item_code = %s
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
		["name", "parent", "item_code", "docstatus", "received_qty", "qty"],
		as_dict=True,
	)
	if not pr_item or pr_item.docstatus != 1:
		frappe.throw(_("Row {0}: Purchase Receipt must be submitted.").format(allocation.idx))
	if pr_item.parent != allocation.purchase_receipt or pr_item.item_code != doc.custom_qc_item:
		frappe.throw(
			_("Row {0}: Purchase Receipt row does not match the selected Item.").format(allocation.idx)
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
	allocation.received_qty = received_qty
	allocation.already_inspected_qty = inspected_qty
	allocation.pending_qty = pending_qty
	allocation.remaining_qty = pending_qty - accepted_qty - rejected_qty


def _get_inspected_qty(purchase_receipt_item, exclude_quality_inspection=None):
	conditions = ["qci.purchase_receipt_item = %s", "qi.docstatus = 1"]
	values = [purchase_receipt_item]
	if exclude_quality_inspection:
		conditions.append("qi.name != %s")
		values.append(exclude_quality_inspection)

	return flt(
		frappe.db.sql(
			f"""
			SELECT COALESCE(SUM(qci.accepted_qty + qci.rejected_qty), 0)
			FROM `tabQuality Inspection PR Detail` qci
			INNER JOIN `tabQuality Inspection` qi ON qi.name = qci.parent
			WHERE {" AND ".join(conditions)}
			""",
			values,
		)[0][0]
	)


def _get_pending_qty(pr_item, exclude_quality_inspection=None):
	received_qty = flt(pr_item.received_qty) or flt(pr_item.qty)
	return max(received_qty - _get_inspected_qty(pr_item.name, exclude_quality_inspection), 0)
