import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import UnitTestCase
from frappe.utils import flt, getdate, today

from bounce.bounce_infinity.doctype.incoming_quality_inspection.incoming_quality_inspection import (
	create_qc_purchase_returns,
	create_qc_purchase_returns_for_receipt,
	get_pending_qc_rows,
	get_purchase_receipt_inspections,
)


class TestIncomingQualityInspectionE2E(UnitTestCase):
	def test_multiple_grns_workbench_qc_and_stock_transfers(self):
		self._ensure_item_master_data()
		self._ensure_stock_entry_type()
		self.company = self._ensure_company()
		self.company_abbr = frappe.db.get_value("Company", self.company, "abbr")
		self.parent_warehouse = frappe.db.get_value(
			"Warehouse", {"company": self.company, "is_group": 1}, "name"
		)
		if not self.parent_warehouse:
			self.parent_warehouse = (
				frappe.get_doc(
					{
						"doctype": "Warehouse",
						"warehouse_name": "All Warehouses",
						"company": self.company,
						"is_group": 1,
					}
				)
				.insert()
				.name
			)
		supplier_group = frappe.db.get_value("Supplier Group", {}, "name")
		supplier = frappe.db.get_value("Supplier", {"supplier_name": "_Test Supplier"}, "name")
		if not supplier:
			supplier = (
				frappe.get_doc(
					{
						"doctype": "Supplier",
						"supplier_name": "_Test Supplier",
						"supplier_group": supplier_group,
						"supplier_type": "Company",
					}
				)
				.insert()
				.name
			)
		item_a = self._make_item("_Test Incoming QC Item A")
		item_b = self._make_item("_Test Incoming QC Item B")
		accepted_warehouse = self._make_warehouse(
			"_Test Incoming QC Accepted", {"custom_is_qc_accepted_warehouse": 1}
		)
		rejected_warehouse = self._make_warehouse(
			"_Test Incoming QC Rejected", {"custom_is_qc_rejected_warehouse": 1}
		)
		quality_warehouse = self._make_warehouse("_Test Incoming QC Quality", {})
		self.accepted_warehouse = accepted_warehouse
		self.rejected_warehouse = rejected_warehouse
		initial_qty = {
			(item_a.name, quality_warehouse): self._actual_qty(item_a.name, quality_warehouse),
			(item_a.name, accepted_warehouse): self._actual_qty(item_a.name, accepted_warehouse),
			(item_a.name, rejected_warehouse): self._actual_qty(item_a.name, rejected_warehouse),
			(item_b.name, quality_warehouse): self._actual_qty(item_b.name, quality_warehouse),
			(item_b.name, accepted_warehouse): self._actual_qty(item_b.name, accepted_warehouse),
		}

		receipts = [
			self._make_receipt(item_a.name, 30, quality_warehouse, supplier),
			self._make_receipt(item_a.name, 70, quality_warehouse, supplier),
			self._make_receipt(item_b.name, 40, quality_warehouse, supplier),
		]

		all_rows = get_pending_qc_rows()
		created_names = {receipt.name for receipt in receipts}
		created_rows = [row for row in all_rows if row.purchase_receipt in created_names]
		self.assertEqual(len(created_rows), 3)
		self.assertEqual(sum(row.pending_qty for row in created_rows), 140)

		item_rows = get_pending_qc_rows(item_code=item_a.name)
		item_rows = [row for row in item_rows if row.purchase_receipt in created_names]
		self.assertEqual(len(item_rows), 2)
		self.assertEqual(sum(row.pending_qty for row in item_rows), 100)

		receipt_rows = get_pending_qc_rows(purchase_receipt=receipts[0].name)
		self.assertEqual(len(receipt_rows), 1)
		self.assertEqual(receipt_rows[0].pending_qty, 30)

		partial_qc = self._make_qc(item_rows, ((20, 5), (40, 10)), "Partial rejection")
		self.assertTrue(partial_qc.accepted_stock_entry)
		self.assertTrue(partial_qc.rejected_stock_entry)
		self.assertEqual(frappe.db.get_value("Stock Entry", partial_qc.accepted_stock_entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Stock Entry", partial_qc.rejected_stock_entry, "docstatus"), 1)

		for receipt in receipts[:2]:
			status, workflow_state = frappe.db.get_value(
				"Purchase Receipt", receipt.name, ["custom_qc_status", "workflow_state"]
			)
			self.assertEqual((status, workflow_state), ("Partial QC Done", "Partial QC Done"))

		remaining_rows = get_pending_qc_rows(item_code=item_a.name)
		remaining_rows = [row for row in remaining_rows if row.purchase_receipt in created_names]
		self.assertEqual([row.pending_qty for row in remaining_rows], [5, 20])

		item_b_rows = [
			row for row in get_pending_qc_rows(item_code=item_b.name) if row.purchase_receipt in created_names
		]
		final_qc = self._make_qc(remaining_rows + item_b_rows, ((5, 0), (20, 0), (40, 0)))
		self.assertEqual(final_qc.item_code, "Multiple Items")
		self.assertTrue(final_qc.accepted_stock_entry)
		self.assertFalse(final_qc.rejected_stock_entry)
		self.assertFalse(
			[
				row
				for row in get_pending_qc_rows(item_code=item_a.name)
				if row.purchase_receipt in created_names
			]
		)

		for receipt in receipts[:2]:
			status, workflow_state = frappe.db.get_value(
				"Purchase Receipt", receipt.name, ["custom_qc_status", "workflow_state"]
			)
			self.assertEqual(
				(status, workflow_state),
				("QC Completed - Partially Rejected", "QC Completed - Partially Rejected"),
			)

		from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_return

		standard_return = make_purchase_return(receipts[0].name)
		with self.assertRaises(frappe.ValidationError):
			standard_return.insert()

		purchase_returns = []
		for receipt in receipts[:2]:
			purchase_returns.extend(create_qc_purchase_returns_for_receipt(receipt.name))
		self.assertEqual(len(purchase_returns), 2)
		for index, purchase_return_name in enumerate(purchase_returns):
			purchase_return = frappe.get_doc("Purchase Receipt", purchase_return_name)
			self.assertTrue(all(row.warehouse == rejected_warehouse for row in purchase_return.items))
			allocation = frappe.get_doc(
				"Incoming QC Allocation", purchase_return.items[0].custom_incoming_qc_allocation
			)
			purchase_return.items[0].qty = -(allocation.rejected_qty + 1)
			with self.assertRaises(frappe.ValidationError):
				purchase_return.save()
			purchase_return.reload()
			if index == 0:
				partial_return_qty = max(flt(allocation.rejected_qty) - 2, 1)
				purchase_return.items[0].qty = -partial_return_qty
				purchase_return.items[0].received_qty = -partial_return_qty
				purchase_return.save()
			apply_workflow(purchase_return, "Submit Return")
		remaining_returns = create_qc_purchase_returns(partial_qc.name)
		self.assertEqual(len(remaining_returns), 1)
		apply_workflow(frappe.get_doc("Purchase Receipt", remaining_returns[0]), "Submit Return")
		self.assertFalse(create_qc_purchase_returns(partial_qc.name))

		self.assertEqual(
			frappe.db.get_value("Purchase Receipt", receipts[2].name, ["custom_qc_status", "workflow_state"]),
			("QC Completed - Fully Accepted", "QC Completed - Fully Accepted"),
		)

		related_inspections = get_purchase_receipt_inspections(receipts[0].name)
		self.assertEqual(
			{inspection.name for inspection in related_inspections},
			{partial_qc.name, final_qc.name},
		)

		self.assertEqual(
			self._actual_qty(item_a.name, quality_warehouse), initial_qty[item_a.name, quality_warehouse]
		)
		self.assertEqual(
			self._actual_qty(item_a.name, accepted_warehouse),
			initial_qty[item_a.name, accepted_warehouse] + 85,
		)
		self.assertEqual(
			self._actual_qty(item_a.name, rejected_warehouse),
			initial_qty[item_a.name, rejected_warehouse],
		)
		self.assertEqual(
			self._actual_qty(item_b.name, quality_warehouse),
			initial_qty[item_b.name, quality_warehouse],
		)
		self.assertEqual(
			self._actual_qty(item_b.name, accepted_warehouse),
			initial_qty[item_b.name, accepted_warehouse] + 40,
		)

	def _make_receipt(self, item_code, qty, warehouse, supplier):
		receipt = frappe.get_doc(
			{
				"doctype": "Purchase Receipt",
				"company": self.company,
				"supplier": supplier,
				"items": [
					{
						"item_code": item_code,
						"qty": qty,
						"received_qty": qty,
						"warehouse": warehouse,
						"rate": 50,
						"conversion_factor": 1,
					},
				],
			}
		)
		receipt.insert()
		apply_workflow(receipt, "Approve")
		return frappe.get_doc("Purchase Receipt", receipt.name)

	def _make_item(self, item_code):
		if frappe.db.exists("Item", item_code):
			return frappe.get_doc("Item", item_code)
		return frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": self.item_group,
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert()

	def _ensure_item_master_data(self):
		if not frappe.db.exists("UOM", "Nos"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Nos", "must_be_whole_number": 1}).insert()

		self.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if self.item_group:
			return

		parent_item_group = frappe.db.get_value("Item Group", {"is_group": 1}, "name")
		if not parent_item_group:
			parent_item_group = (
				frappe.get_doc(
					{
						"doctype": "Item Group",
						"item_group_name": "All Item Groups",
						"is_group": 1,
					}
				)
				.insert()
				.name
			)
		self.item_group = (
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "_Test Incoming QC Items",
					"parent_item_group": parent_item_group,
					"is_group": 0,
				}
			)
			.insert()
			.name
		)

	def _ensure_company(self):
		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			if not frappe.db.exists("Warehouse Type", "Transit"):
				frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert()
			company = (
				frappe.get_doc(
					{
						"doctype": "Company",
						"company_name": "_Test Incoming QC Company",
						"abbr": "IQC",
						"country": "India",
						"default_currency": "INR",
						"create_chart_of_accounts_based_on": "Standard Template",
						"chart_of_accounts": "Standard",
					}
				)
				.insert()
				.name
			)

		posting_date = getdate(today())
		fiscal_year = frappe.db.get_value(
			"Fiscal Year",
			{
				"year_start_date": ["<=", posting_date],
				"year_end_date": [">=", posting_date],
			},
			"name",
		)
		if not fiscal_year:
			frappe.get_doc(
				{
					"doctype": "Fiscal Year",
					"year": f"_Test Incoming QC FY {posting_date.year}",
					"year_start_date": posting_date.replace(month=1, day=1),
					"year_end_date": posting_date.replace(month=12, day=31),
				}
			).insert()
		return company

	def _ensure_stock_entry_type(self):
		if frappe.db.exists("Stock Entry Type", "Material Transfer"):
			return
		frappe.get_doc(
			{
				"doctype": "Stock Entry Type",
				"name": "Material Transfer",
				"purpose": "Material Transfer",
				"is_standard": 1,
			}
		).insert()

	def _make_warehouse(self, warehouse_name, properties):
		name = f"{warehouse_name} - {self.company_abbr}"
		if frappe.db.exists("Warehouse", name):
			warehouse = frappe.get_doc("Warehouse", name)
			warehouse.update(properties)
			warehouse.save()
			return warehouse.name
		return (
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": warehouse_name,
					"company": self.company,
					"parent_warehouse": self.parent_warehouse,
					**properties,
				}
			)
			.insert()
			.name
		)

	def _make_qc(self, rows, quantities, rejection_reason=None):
		inspection = frappe.get_doc(
			{
				"doctype": "Incoming Quality Inspection",
				"company": rows[0].company,
				"item_code": rows[0].item_code,
				"accepted_warehouse": self.accepted_warehouse,
				"rejected_warehouse": self.rejected_warehouse,
				"rejection_reason": rejection_reason,
				"allocations": [
					{
						"purchase_receipt": row.purchase_receipt,
						"purchase_receipt_item": row.purchase_receipt_item,
						"accepted_qty": quantities[index][0],
						"rejected_qty": quantities[index][1],
					}
					for index, row in enumerate(rows)
				],
			}
		)
		inspection.insert()
		inspection.submit()
		return inspection

	def _actual_qty(self, item_code, warehouse):
		return frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0
