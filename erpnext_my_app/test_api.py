import frappe
import unittest
from erpnext_my_app.api import export_delivery_notes_to_csv

class TestExportDeliveryNotesToCsv(unittest.TestCase):
    def test_export_delivery_notes_to_csv(self):
        # 准备测试数据（你可以用 frappe.get_doc().insert() 来插入）
        # dn1 = frappe.get_doc({
        #     "doctype": "Delivery Note",
        #     "customer": "_Test Customer",
        #     "items": [{
        #         "item_code": "_Test Item",
        #         "qty": 1
        #     }]
        # }).insert()

        # 调用 API
        result = export_delivery_notes_to_csv("MAT-DN-2025-06493")
        self.assertIn("file_url", result["message"])
