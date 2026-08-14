from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from bounce.supplier_warranty import _calculate_claim, populate_warranty_claim


class TestSupplierWarranty(UnitTestCase):
	def test_supplier_claim_amount_uses_rate_times_multiplier(self):
		serial = frappe.new_doc("Serial No")
		serial.custom_original_purchase_rate = 1000
		serial.custom_supplier_claim_multiplier = 2
		_calculate_claim(serial)
		self.assertEqual(serial.custom_supplier_claim_amount, 2000)

	def test_warranty_claim_fetches_supplier_origin_from_serial(self):
		serial = frappe.new_doc("Serial No")
		serial.name = "_Test Supplier Warranty Serial"
		serial.item_code = "_Test Item"
		serial.company = "_Test Company"
		serial.custom_supplier = "_Test Supplier"
		serial.custom_original_purchase_receipt = "MAT-PRE-TEST"
		serial.custom_original_purchase_rate = 750
		serial.custom_supplier_claim_multiplier = 2

		claim = frappe.new_doc("Warranty Claim")
		claim.serial_no = serial.name
		with patch("bounce.supplier_warranty.frappe.get_doc", return_value=serial):
			populate_warranty_claim(claim)

		self.assertEqual(claim.custom_supplier, "_Test Supplier")
		self.assertEqual(claim.custom_original_purchase_receipt, "MAT-PRE-TEST")
		self.assertEqual(claim.custom_supplier_claim_amount, 1500)
