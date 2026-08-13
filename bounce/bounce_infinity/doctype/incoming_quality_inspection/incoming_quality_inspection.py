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
		self._validate_destination_warehouses()
		self.total_pending_qty = totals["pending"]
		self.total_accepted_qty = totals["accepted"]
		self.total_rejected_qty = totals["rejected"]
		self.total_remaining_qty = totals["remaining"]

	def _validate_destination_warehouses(self):
		if self.accepted_warehouse == self.rejected_warehouse:
			frappe.throw(_("Accepted and rejected warehouses must be different."))
		_validate_destination_warehouse(
			self.accepted_warehouse, self.company, "custom_is_qc_accepted_warehouse"
		)
		_validate_destination_warehouse(
			self.rejected_warehouse, self.company, "custom_is_qc_rejected_warehouse"
		)
		for allocation in self.allocations:
			if allocation.source_warehouse in (self.accepted_warehouse, self.rejected_warehouse):
				frappe.throw(_("QC source and destination warehouses cannot be the same."))

	def _create_stock_entry(self, quantity_field, result):
		items = []
		for allocation in self.allocations:
			qty = flt(allocation.get(quantity_field))
			if not qty:
				continue
			target_warehouse = self.accepted_warehouse if result == "Accepted" else self.rejected_warehouse
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
			pr.posting_date, pr.supplier, pr.company
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		INNER JOIN `tabWarehouse` warehouse ON warehouse.name = pri.warehouse
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


@frappe.whitelist()
def get_purchase_receipt_inspections(purchase_receipt: str):
	if not purchase_receipt or not frappe.has_permission("Purchase Receipt", "read", purchase_receipt):
		frappe.throw(_("You are not permitted to read this Purchase Receipt."), frappe.PermissionError)
	if not frappe.has_permission("Incoming Quality Inspection", "read"):
		frappe.throw(_("You are not permitted to read Incoming Quality Inspections."), frappe.PermissionError)

	return frappe.db.sql(
		"""
		SELECT DISTINCT iqc.name, iqc.inspection_date, iqc.item_code, iqc.status, iqc.docstatus,
			iqc.total_rejected_qty, iqc.rejected_warehouse
		FROM `tabIncoming Quality Inspection` iqc
		INNER JOIN `tabIncoming QC Allocation` allocation ON allocation.parent = iqc.name
		WHERE allocation.purchase_receipt = %s AND iqc.docstatus < 2
		ORDER BY iqc.inspection_date DESC, iqc.creation DESC
		""",
		(purchase_receipt,),
		as_dict=True,
	)


def clear_qc_status_for_return(doc, method=None):
	if doc.is_return:
		doc.custom_qc_status = ""


def validate_qc_purchase_return(doc, method=None):
	if not doc.is_return or not doc.return_against:
		return
	if not doc.custom_incoming_quality_inspection:
		if _purchase_receipt_has_rejected_qc(doc.return_against):
			frappe.throw(
				_(
					"This Purchase Receipt has QC-rejected quantity. Create its Purchase Return "
					"using Create > QC Purchase Return so the rejected warehouse and quantity are enforced."
				)
			)
		return

	for row in doc.items:
		if not row.custom_incoming_qc_allocation:
			frappe.throw(_("Every QC Purchase Return row must reference an Incoming QC Allocation."))
		allocation = frappe.db.get_value(
			"Incoming QC Allocation",
			row.custom_incoming_qc_allocation,
			[
				"parent",
				"purchase_receipt",
				"purchase_receipt_item",
				"rejected_qty",
			],
			as_dict=True,
		)
		if (
			not allocation
			or allocation.parent != doc.custom_incoming_quality_inspection
			or allocation.purchase_receipt != doc.return_against
			or allocation.purchase_receipt_item != row.purchase_receipt_item
		):
			frappe.throw(_("Row {0}: QC allocation does not match the Purchase Return.").format(row.idx))

		rejected_warehouse = frappe.db.get_value(
			"Incoming Quality Inspection", allocation.parent, "rejected_warehouse"
		)
		if row.warehouse != rejected_warehouse:
			frappe.throw(
				_("Row {0}: Warehouse must be the rejected warehouse {1}.").format(
					row.idx, rejected_warehouse
				)
			)
		already_returned = _get_returned_rejected_qty(
			row.custom_incoming_qc_allocation, exclude_purchase_return=doc.name
		)
		if abs(flt(row.qty)) > flt(allocation.rejected_qty) - already_returned:
			frappe.throw(
				_("Row {0}: Return quantity exceeds the remaining rejected quantity.").format(row.idx)
			)


@frappe.whitelist()
def create_qc_purchase_returns(inspection: str, purchase_receipt: str | None = None):
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_return

	doc = frappe.get_doc("Incoming Quality Inspection", inspection)
	doc.check_permission("read")
	if doc.docstatus != 1 or not doc.total_rejected_qty:
		frappe.throw(_("Submit an Incoming Quality Inspection with rejected quantity first."))
	if not frappe.has_permission("Purchase Receipt", "create"):
		frappe.throw(_("You are not permitted to create Purchase Receipts."), frappe.PermissionError)

	allocations_by_receipt = {}
	for allocation in doc.allocations:
		if purchase_receipt and allocation.purchase_receipt != purchase_receipt:
			continue
		remaining = flt(allocation.rejected_qty) - _get_returned_rejected_qty(allocation.name)
		if remaining > 0:
			allocations_by_receipt.setdefault(allocation.purchase_receipt, {})[
				allocation.purchase_receipt_item
			] = (allocation, remaining)

	created = []
	for purchase_receipt, allocation_map in allocations_by_receipt.items():
		purchase_return = make_purchase_return(purchase_receipt)
		purchase_return.custom_incoming_quality_inspection = doc.name
		for row in list(purchase_return.items):
			allocation_data = allocation_map.get(row.purchase_receipt_item)
			if not allocation_data:
				purchase_return.remove(row)
				continue
			allocation, remaining = allocation_data
			row.qty = -remaining
			row.received_qty = -remaining
			row.stock_qty = -remaining * flt(row.conversion_factor or 1)
			row.warehouse = doc.rejected_warehouse
			row.custom_incoming_qc_allocation = allocation.name
		purchase_return.insert()
		created.append(purchase_return.name)
	return created


@frappe.whitelist()
def create_qc_purchase_returns_for_receipt(purchase_receipt: str):
	if not frappe.has_permission("Purchase Receipt", "read", purchase_receipt):
		frappe.throw(_("You are not permitted to read this Purchase Receipt."), frappe.PermissionError)
	inspections = frappe.db.sql(
		"""
		SELECT DISTINCT iqc.name
		FROM `tabIncoming Quality Inspection` iqc
		INNER JOIN `tabIncoming QC Allocation` allocation ON allocation.parent = iqc.name
		WHERE allocation.purchase_receipt = %s AND iqc.docstatus = 1
			AND allocation.rejected_qty > 0
		ORDER BY iqc.creation
		""",
		(purchase_receipt,),
		pluck=True,
	)
	created = []
	for inspection in inspections:
		created.extend(create_qc_purchase_returns(inspection, purchase_receipt))
	return created


def _purchase_receipt_has_rejected_qc(purchase_receipt):
	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM `tabIncoming QC Allocation` allocation
			INNER JOIN `tabIncoming Quality Inspection` iqc ON iqc.name = allocation.parent
			WHERE allocation.purchase_receipt = %s AND iqc.docstatus = 1
				AND allocation.rejected_qty > 0
			LIMIT 1
			""",
			(purchase_receipt,),
		)
	)


def _get_returned_rejected_qty(allocation, exclude_purchase_return=None):
	if exclude_purchase_return:
		query = """
			SELECT COALESCE(SUM(ABS(pri.qty)), 0)
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.custom_incoming_qc_allocation = %s
				AND pr.is_return = 1 AND pr.docstatus = 1 AND pr.name != %s
		"""
		values = (allocation, exclude_purchase_return)
	else:
		query = """
			SELECT COALESCE(SUM(ABS(pri.qty)), 0)
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.custom_incoming_qc_allocation = %s
				AND pr.is_return = 1 AND pr.docstatus = 1
		"""
		values = (allocation,)
	return flt(frappe.db.sql(query, values)[0][0])


def _get_purchase_receipt_item(row_name, lock_row=False):
	lock_row = lock_row and frappe.db.db_type != "sqlite"
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
		["company", "is_group", "disabled"],
		as_dict=True,
	)
	if not warehouse or warehouse.disabled or warehouse.is_group or warehouse.company != company:
		frappe.throw(_("Warehouse {0} is not a valid QC source warehouse.").format(source_warehouse))


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
			rejected_qty = flt(
				frappe.db.sql(
					"""
					SELECT COALESCE(SUM(qca.rejected_qty), 0)
					FROM `tabIncoming QC Allocation` qca
					INNER JOIN `tabIncoming Quality Inspection` iqc ON iqc.name = qca.parent
					WHERE qca.purchase_receipt = %s AND iqc.docstatus = 1
					""",
					(purchase_receipt,),
				)[0][0]
			)
			status = "QC Completed - Partially Rejected" if rejected_qty else "QC Completed - Fully Accepted"
		frappe.db.set_value(
			"Purchase Receipt",
			purchase_receipt,
			{"custom_qc_status": status, "workflow_state": _get_purchase_receipt_workflow_state(status)},
		)


def _get_purchase_receipt_workflow_state(qc_status):
	return "Approved" if qc_status == "QC Pending" else qc_status
