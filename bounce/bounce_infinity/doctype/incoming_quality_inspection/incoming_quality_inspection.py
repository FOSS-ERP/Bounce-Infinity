import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class IncomingQualityInspection(Document):
	def before_insert(self):
		self.status = "Draft"

	def validate(self):
		self._validate_allocations(lock_rows=False)

	def before_submit(self):
		self._validate_allocations(lock_rows=True)
		if not self.total_accepted_qty and not self.total_rejected_qty:
			frappe.throw(_("Enter an accepted or rejected quantity before submitting."))
		if self.total_rejected_qty and not self.rejection_reason:
			frappe.throw(_("Rejection Reason is required when rejected quantity is greater than zero."))
		self.status = "Submitted"

	def on_submit(self):
		accepted_entry = self._create_stock_entry("accepted_qty", "Accepted")
		rejected_entry = self._create_stock_entry("rejected_qty", "Rejected")
		if accepted_entry:
			self.db_set("accepted_stock_entry", accepted_entry, update_modified=False)
		if rejected_entry:
			self.db_set("rejected_stock_entry", rejected_entry, update_modified=False)
		_update_purchase_receipt_qc_statuses(self.allocations)

	def before_cancel(self):
		for fieldname in ("accepted_stock_entry", "rejected_stock_entry"):
			stock_entry = self.get(fieldname)
			if stock_entry and frappe.db.get_value("Stock Entry", stock_entry, "docstatus") == 1:
				frappe.get_doc("Stock Entry", stock_entry).cancel()

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)
		_update_purchase_receipt_qc_statuses(self.allocations)

	def _validate_allocations(self, lock_rows=False):
		if not self.allocations:
			frappe.throw(_("Select at least one pending Purchase Receipt row."))

		seen_rows = set()
		items = set()
		companies = set()
		totals = {"pending": 0.0, "accepted": 0.0, "rejected": 0.0, "remaining": 0.0}

		for allocation in self.allocations:
			if allocation.purchase_receipt_item in seen_rows:
				frappe.throw(
					_("Row {0}: Purchase Receipt row is selected more than once.").format(allocation.idx)
				)
			seen_rows.add(allocation.purchase_receipt_item)

			pr_item = _get_purchase_receipt_item(allocation.purchase_receipt_item, lock_rows)
			if not pr_item or pr_item.docstatus != 1 or pr_item.is_return:
				frappe.throw(
					_("Row {0}: Purchase Receipt must be submitted and cannot be a return.").format(
						allocation.idx
					)
				)
			if pr_item.parent != allocation.purchase_receipt:
				frappe.throw(
					_("Row {0}: Purchase Receipt row does not match its parent.").format(allocation.idx)
				)

			_validate_qc_warehouse(pr_item.warehouse, pr_item.company)
			pending_qty = _get_pending_qty(pr_item, self.name)
			accepted_qty = flt(allocation.accepted_qty)
			rejected_qty = flt(allocation.rejected_qty)
			if accepted_qty < 0 or rejected_qty < 0:
				frappe.throw(_("Row {0}: quantities cannot be negative.").format(allocation.idx))
			if accepted_qty + rejected_qty > pending_qty:
				frappe.throw(
					_("Row {0}: accepted plus rejected cannot exceed pending quantity {1}.").format(
						allocation.idx, pending_qty
					)
				)

			inspected_qty = _get_inspected_qty(pr_item.name, self.name)
			allocation.update(
				{
					"posting_date": pr_item.posting_date,
					"supplier": pr_item.supplier,
					"item_code": pr_item.item_code,
					"source_warehouse": pr_item.warehouse,
					"received_qty": pr_item.received_qty,
					"already_inspected_qty": inspected_qty,
					"pending_qty": pending_qty,
					"remaining_qty": pending_qty - accepted_qty - rejected_qty,
				}
			)
			items.add(pr_item.item_code)
			companies.add(pr_item.company)
			totals["pending"] += pending_qty
			totals["accepted"] += accepted_qty
			totals["rejected"] += rejected_qty
			totals["remaining"] += allocation.remaining_qty

		if len(items) != 1:
			frappe.throw(_("All selected Purchase Receipt rows must contain the same Item."))
		if len(companies) != 1:
			frappe.throw(_("All selected Purchase Receipts must belong to the same Company."))

		self.item_code = items.pop()
		self.company = companies.pop()
		self.total_pending_qty = totals["pending"]
		self.total_accepted_qty = totals["accepted"]
		self.total_rejected_qty = totals["rejected"]
		self.total_remaining_qty = totals["remaining"]

	def _create_stock_entry(self, quantity_field, result):
		items = []
		for allocation in self.allocations:
			qty = flt(allocation.get(quantity_field))
			if not qty:
				continue
			route_field = (
				"custom_qc_accepted_warehouse" if result == "Accepted" else "custom_qc_rejected_warehouse"
			)
			target_warehouse = frappe.db.get_value("Warehouse", allocation.source_warehouse, route_field)
			items.append(
				{
					"item_code": allocation.item_code,
					"qty": qty,
					"s_warehouse": allocation.source_warehouse,
					"t_warehouse": target_warehouse,
					"custom_purchase_receipt": allocation.purchase_receipt,
					"custom_purchase_receipt_item": allocation.purchase_receipt_item,
					"custom_incoming_qc_allocation": allocation.name,
				}
			)
		if not items:
			return None

		stock_entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Transfer",
				"purpose": "Material Transfer",
				"company": self.company,
				"custom_incoming_quality_inspection": self.name,
				"custom_qc_result": result,
				"remarks": _("Automatic {0} transfer for {1}").format(result, self.name),
				"items": items,
			}
		)
		stock_entry.insert()
		stock_entry.submit()
		return stock_entry.name


@frappe.whitelist()
def get_pending_qc_rows(
	item_code: str | None = None,
	purchase_receipt: str | None = None,
	supplier: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
):
	if not frappe.has_permission("Incoming Quality Inspection", "create"):
		frappe.throw(
			_("You are not permitted to create Incoming Quality Inspections."), frappe.PermissionError
		)
	if not frappe.has_permission("Purchase Receipt", "read"):
		frappe.throw(_("You are not permitted to read Purchase Receipts."), frappe.PermissionError)

	values = (
		item_code or None,
		item_code or None,
		purchase_receipt or None,
		purchase_receipt or None,
		supplier or None,
		supplier or None,
		from_date or None,
		from_date or None,
		to_date or None,
		to_date or None,
	)
	rows = frappe.db.sql(
		"""
		SELECT pri.name AS purchase_receipt_item, pri.parent AS purchase_receipt,
			pri.item_code, pri.warehouse AS source_warehouse,
			COALESCE(NULLIF(pri.received_qty, 0), pri.qty, 0) AS received_qty,
			pr.posting_date, pr.supplier, pr.company,
			CASE WHEN accepted_warehouse.name IS NOT NULL
				AND accepted_warehouse.disabled = 0 AND accepted_warehouse.is_group = 0
				AND accepted_warehouse.custom_is_qc_accepted_warehouse = 1
				AND accepted_warehouse.company = pr.company
				AND rejected_warehouse.name IS NOT NULL
				AND rejected_warehouse.disabled = 0 AND rejected_warehouse.is_group = 0
				AND rejected_warehouse.custom_is_qc_rejected_warehouse = 1
				AND rejected_warehouse.company = pr.company
			THEN 1 ELSE 0 END AS route_configured
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		INNER JOIN `tabWarehouse` warehouse ON warehouse.name = pri.warehouse
		LEFT JOIN `tabWarehouse` accepted_warehouse
			ON accepted_warehouse.name = warehouse.custom_qc_accepted_warehouse
		LEFT JOIN `tabWarehouse` rejected_warehouse
			ON rejected_warehouse.name = warehouse.custom_qc_rejected_warehouse
		WHERE pr.docstatus = 1 AND pr.is_return = 0
			AND warehouse.disabled = 0 AND warehouse.is_group = 0
			AND (%s IS NULL OR pri.item_code = %s)
			AND (%s IS NULL OR pr.name = %s)
			AND (%s IS NULL OR pr.supplier = %s)
			AND (%s IS NULL OR pr.posting_date >= %s)
			AND (%s IS NULL OR pr.posting_date <= %s)
		ORDER BY pr.posting_date, pr.posting_time, pr.name, pri.idx
		""",
		values,
		as_dict=True,
	)

	result = []
	permission_cache = {}
	for row in rows:
		if row.purchase_receipt not in permission_cache:
			permission_cache[row.purchase_receipt] = frappe.has_permission(
				"Purchase Receipt", "read", row.purchase_receipt
			)
		if not permission_cache[row.purchase_receipt]:
			continue
		inspected_qty = _get_inspected_qty(row.purchase_receipt_item)
		pending_qty = max(flt(row.received_qty) - inspected_qty, 0)
		if pending_qty:
			row.update(
				{
					"inspected_qty": inspected_qty,
					"pending_qty": pending_qty,
					"qc_status": "Partial QC Done" if inspected_qty else "QC Pending",
				}
			)
			result.append(row)
	return result


def clear_qc_status_for_return(doc, method=None):
	if doc.is_return:
		doc.custom_qc_status = ""


def validate_warehouse_qc_routes(doc, method=None):
	accepted_warehouse = doc.get("custom_qc_accepted_warehouse")
	rejected_warehouse = doc.get("custom_qc_rejected_warehouse")
	if bool(accepted_warehouse) != bool(rejected_warehouse):
		frappe.throw(_("Set both accepted and rejected QC warehouses, or leave both empty."))
	if accepted_warehouse:
		if doc.is_group or doc.disabled:
			frappe.throw(_("A disabled or group Warehouse cannot be configured as a QC source."))
		if doc.name in (accepted_warehouse, rejected_warehouse):
			frappe.throw(_("QC source and destination warehouses cannot be the same."))
		if accepted_warehouse == rejected_warehouse:
			frappe.throw(_("Accepted and rejected QC warehouses must be different."))
		_validate_destination_warehouse(accepted_warehouse, doc.company, "custom_is_qc_accepted_warehouse")
		_validate_destination_warehouse(rejected_warehouse, doc.company, "custom_is_qc_rejected_warehouse")


def _get_purchase_receipt_item(row_name, lock_row=False):
	if lock_row:
		query = """
			SELECT pri.name, pri.parent, pri.item_code, pri.warehouse, pri.docstatus,
				COALESCE(NULLIF(pri.received_qty, 0), pri.qty, 0) AS received_qty,
				pr.posting_date, pr.supplier, pr.company, pr.is_return
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.name = %s FOR UPDATE
		"""
	else:
		query = """
			SELECT pri.name, pri.parent, pri.item_code, pri.warehouse, pri.docstatus,
				COALESCE(NULLIF(pri.received_qty, 0), pri.qty, 0) AS received_qty,
				pr.posting_date, pr.supplier, pr.company, pr.is_return
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.name = %s
		"""
	rows = frappe.db.sql(query, (row_name,), as_dict=True)
	return rows[0] if rows else None


def _validate_qc_warehouse(source_warehouse, company):
	warehouse = frappe.db.get_value(
		"Warehouse",
		source_warehouse,
		["company", "is_group", "disabled", "custom_qc_accepted_warehouse", "custom_qc_rejected_warehouse"],
		as_dict=True,
	)
	if not warehouse or warehouse.disabled or warehouse.is_group or warehouse.company != company:
		frappe.throw(_("Warehouse {0} is not a valid QC source warehouse.").format(source_warehouse))
	if not warehouse.custom_qc_accepted_warehouse or not warehouse.custom_qc_rejected_warehouse:
		frappe.throw(_("Configure accepted and rejected QC warehouses on {0}.").format(source_warehouse))
	if source_warehouse in (warehouse.custom_qc_accepted_warehouse, warehouse.custom_qc_rejected_warehouse):
		frappe.throw(_("QC source and destination warehouses cannot be the same."))
	if warehouse.custom_qc_accepted_warehouse == warehouse.custom_qc_rejected_warehouse:
		frappe.throw(_("Accepted and rejected QC warehouses must be different."))
	_validate_destination_warehouse(
		warehouse.custom_qc_accepted_warehouse, company, "custom_is_qc_accepted_warehouse"
	)
	_validate_destination_warehouse(
		warehouse.custom_qc_rejected_warehouse, company, "custom_is_qc_rejected_warehouse"
	)


def _validate_destination_warehouse(warehouse_name, company, classification_field):
	destination = frappe.db.get_value(
		"Warehouse",
		warehouse_name,
		["company", "is_group", "disabled", classification_field],
		as_dict=True,
	)
	if (
		not destination
		or destination.company != company
		or destination.is_group
		or destination.disabled
		or not destination.get(classification_field)
	):
		frappe.throw(_("Warehouse {0} is not a valid classified QC destination.").format(warehouse_name))


def _get_inspected_qty(purchase_receipt_item, exclude_inspection=None):
	legacy_inspection = frappe.db.exists(
		"Quality Inspection",
		{
			"docstatus": 1,
			"reference_type": "Purchase Receipt",
			"child_row_reference": purchase_receipt_item,
		},
	)
	if legacy_inspection:
		quantities = frappe.db.get_value(
			"Purchase Receipt Item", purchase_receipt_item, ["received_qty", "qty"], as_dict=True
		)
		return flt(quantities.received_qty) or flt(quantities.qty)

	if exclude_inspection:
		query = """
			SELECT COALESCE(SUM(qca.accepted_qty + qca.rejected_qty), 0)
			FROM `tabIncoming QC Allocation` qca
			INNER JOIN `tabIncoming Quality Inspection` iqc ON iqc.name = qca.parent
			WHERE qca.purchase_receipt_item = %s AND iqc.docstatus = 1 AND iqc.name != %s
		"""
		values = (purchase_receipt_item, exclude_inspection)
	else:
		query = """
			SELECT COALESCE(SUM(qca.accepted_qty + qca.rejected_qty), 0)
			FROM `tabIncoming QC Allocation` qca
			INNER JOIN `tabIncoming Quality Inspection` iqc ON iqc.name = qca.parent
			WHERE qca.purchase_receipt_item = %s AND iqc.docstatus = 1
		"""
		values = (purchase_receipt_item,)
	return flt(frappe.db.sql(query, values)[0][0])


def _get_pending_qty(pr_item, exclude_inspection=None):
	return max(flt(pr_item.received_qty) - _get_inspected_qty(pr_item.name, exclude_inspection), 0)


def _update_purchase_receipt_qc_statuses(allocations):
	for purchase_receipt in {row.purchase_receipt for row in allocations if row.purchase_receipt}:
		pr_items = frappe.db.sql(
			"""
			SELECT pri.name, COALESCE(NULLIF(pri.received_qty, 0), pri.qty, 0) received_qty
			FROM `tabPurchase Receipt Item` pri
			WHERE pri.parent = %s
			""",
			(purchase_receipt,),
			as_dict=True,
		)
		received_qty = sum(flt(row.received_qty) for row in pr_items)
		inspected_qty = sum(_get_inspected_qty(row.name) for row in pr_items)
		if not inspected_qty:
			status = "QC Pending"
		elif inspected_qty < received_qty:
			status = "Partial QC Done"
		else:
			status = "QC Completed"
		frappe.db.set_value(
			"Purchase Receipt",
			purchase_receipt,
			{"custom_qc_status": status, "workflow_state": _get_purchase_receipt_workflow_state(status)},
		)


def _get_purchase_receipt_workflow_state(qc_status):
	return "Approved" if qc_status == "QC Pending" else qc_status
