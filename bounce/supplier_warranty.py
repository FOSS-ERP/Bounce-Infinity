import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


def populate_serial_purchase_origin(doc: Document, method: str | None = None):
	if doc.reference_doctype != "Purchase Receipt" or not doc.reference_name:
		return
	pr = frappe.get_doc("Purchase Receipt", doc.reference_name)
	if pr.docstatus != 1:
		return
	row = _find_purchase_receipt_item(pr, doc.name, doc.item_code)
	if not row:
		return
	doc.custom_supplier = pr.supplier
	doc.custom_supplier_name = pr.supplier_name
	doc.custom_original_purchase_receipt = pr.name
	doc.custom_original_purchase_receipt_item = row.name
	doc.custom_original_purchase_rate = row.rate
	doc.custom_supplier_invoice_no = pr.supplier_delivery_note
	doc.custom_supplier_invoice_date = pr.posting_date
	_calculate_claim(doc)


def populate_purchase_receipt_serials(doc: Document, method: str | None = None):
	if doc.is_return:
		return
	for row in doc.items:
		serial_nos = []
		if row.serial_and_batch_bundle:
			serial_nos = frappe.get_all(
				"Serial and Batch Entry",
				filters={"parent": row.serial_and_batch_bundle},
				pluck="serial_no",
			)
		serial_nos.extend((row.get("serial_no") or "").replace(",", "\n").split())
		for serial_no in set(serial_nos):
			serial = frappe.get_doc("Serial No", serial_no)
			serial.reference_doctype = "Purchase Receipt"
			serial.reference_name = doc.name
			populate_serial_purchase_origin(serial)
			serial.save(ignore_permissions=True)


def populate_warranty_claim(doc: Document, method: str | None = None):
	if not doc.serial_no:
		return
	serial = frappe.get_doc("Serial No", doc.serial_no)
	for field in (
		"custom_supplier",
		"custom_original_purchase_receipt",
		"custom_original_purchase_rate",
		"custom_purchase_return",
		"custom_supplier_debit_note",
	):
		doc.set(field, serial.get(field))
	doc.custom_supplier_claim_multiplier = serial.custom_supplier_claim_multiplier or 2
	doc.custom_supplier_claim_amount = flt(doc.custom_original_purchase_rate) * flt(
		doc.custom_supplier_claim_multiplier
	)
	if serial.maintenance_status == "Out of Warranty" and not {
		"Warranty Manager",
		"System Manager",
	}.intersection(frappe.get_roles()):
		doc.custom_supplier_warranty_claim_required = 0


def _find_purchase_receipt_item(pr: Document, serial_no: str, item_code: str):
	for row in pr.items:
		if row.item_code != item_code:
			continue
		if row.serial_and_batch_bundle and frappe.db.exists(
			"Serial and Batch Entry", {"parent": row.serial_and_batch_bundle, "serial_no": serial_no}
		):
			return row
		if serial_no in (row.get("serial_no") or "").replace(",", "\n").split():
			return row


def _calculate_claim(doc: Document):
	if (
		not doc.is_new()
		and doc.has_value_changed("custom_supplier_claim_multiplier")
		and not {
			"Warranty Manager",
			"System Manager",
		}.intersection(frappe.get_roles())
	):
		frappe.throw(_("Only a Warranty Manager can change the supplier claim multiplier."))
	doc.custom_supplier_claim_multiplier = doc.custom_supplier_claim_multiplier or 2
	doc.custom_supplier_claim_amount = flt(doc.custom_original_purchase_rate) * flt(
		doc.custom_supplier_claim_multiplier
	)


def _get_serial(serial_no: str):
	doc = frappe.get_doc("Serial No", serial_no)
	doc.check_permission("read")
	if (
		not doc.custom_supplier
		or not doc.custom_original_purchase_receipt
		or not doc.custom_original_purchase_receipt_item
	):
		frappe.throw(_("Supplier purchase origin is missing for Serial No {0}.").format(serial_no))
	return doc


@frappe.whitelist()
def create_supplier_return(serial_no: str, warranty_claim: str | None = None):
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_return

	serial = _get_serial(serial_no)
	if not frappe.has_permission("Purchase Receipt", "create"):
		frappe.throw(_("Purchase Receipt create permission is required."), frappe.PermissionError)
	if (
		serial.custom_purchase_return
		and frappe.db.get_value("Purchase Receipt", serial.custom_purchase_return, "docstatus") != 2
	):
		frappe.throw(_("Supplier Warranty Return already exists: {0}").format(serial.custom_purchase_return))
	if not serial.warehouse:
		frappe.throw(
			_("Serial No {0} must be received into a warehouse before supplier return.").format(serial.name)
		)
	ret = make_purchase_return(serial.custom_original_purchase_receipt)
	for row in list(ret.items):
		if row.purchase_receipt_item != serial.custom_original_purchase_receipt_item:
			ret.remove(row)
			continue
		row.qty = row.received_qty = row.stock_qty = -1
		row.warehouse = serial.warehouse
		row.serial_and_batch_bundle = None
		row.use_serial_batch_fields = 1
		row.serial_no = serial.name
	ret.custom_supplier_warranty_serial = serial.name
	ret.custom_warranty_claim = warranty_claim
	ret.insert()
	serial.db_set({"custom_purchase_return": ret.name, "custom_supplier_claim_status": "Claimed"})
	_update_warranty_claim(warranty_claim, "custom_purchase_return", ret.name)
	return ret.name


@frappe.whitelist()
def create_warranty_debit_note(serial_no: str, warranty_claim: str | None = None):
	serial = _get_serial(serial_no)
	if not frappe.has_permission("Purchase Invoice", "create"):
		frappe.throw(_("Purchase Invoice create permission is required."), frappe.PermissionError)
	if (
		serial.custom_supplier_debit_note
		and frappe.db.get_value("Purchase Invoice", serial.custom_supplier_debit_note, "docstatus") != 2
	):
		frappe.throw(_("Warranty Debit Note already exists: {0}").format(serial.custom_supplier_debit_note))
	_calculate_claim(serial)
	pr = frappe.get_doc("Purchase Receipt", serial.custom_original_purchase_receipt)
	pr_item = frappe.get_doc("Purchase Receipt Item", serial.custom_original_purchase_receipt_item)
	invoice = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": pr.company,
			"supplier": pr.supplier,
			"posting_date": today(),
			"is_return": 1,
			"update_stock": 0,
			"custom_supplier_warranty_serial": serial.name,
			"custom_warranty_claim": warranty_claim,
			"items": [
				{
					"item_code": serial.item_code,
					"qty": -1,
					"rate": serial.custom_supplier_claim_amount,
					"expense_account": pr_item.expense_account,
					"cost_center": pr_item.cost_center,
				}
			],
		}
	)
	invoice.insert()
	serial.db_set("custom_supplier_debit_note", invoice.name)
	_update_warranty_claim(warranty_claim, "custom_supplier_debit_note", invoice.name)
	return invoice.name


def _update_warranty_claim(name: str | None, field: str, value: str):
	if name:
		frappe.db.set_value("Warranty Claim", name, field, value)


def sync_purchase_return(doc: Document, method: str | None = None):
	if doc.is_return and doc.custom_supplier_warranty_serial:
		status = "Claimed" if doc.docstatus == 1 else "Pending"
		frappe.db.set_value(
			"Serial No", doc.custom_supplier_warranty_serial, "custom_supplier_claim_status", status
		)


def sync_debit_note(doc: Document, method: str | None = None):
	if doc.is_return and doc.custom_supplier_warranty_serial:
		status = "Settled" if doc.docstatus == 1 else "Claimed"
		frappe.db.set_value(
			"Serial No", doc.custom_supplier_warranty_serial, "custom_supplier_claim_status", status
		)
