import frappe
import unittest
from erpnext_my_app.api import export_delivery_notes_to_csv

class TestExportDeliveryNotesToCsv(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_export_delivery_notes_to_csv(self):
        # 1. 创建客户
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "测试客户",
            "customer_group": "Commercial",
            "territory": "All Territories",
            "mobile_no": "1234567890"
        }).insert(ignore_if_duplicate=True)

        # 2. 创建商品
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": "测试商品",
            "item_name": "测试商品",
            "item_group": "All Item Groups",
            "stock_uom": "Nos",
            "is_stock_item": 0
        }).insert(ignore_if_duplicate=True)

        # 3. 创建地址
        address = frappe.get_doc({
            "doctype": "Address",
            "address_title": "测试客户地址",
            "address_type": "Shipping",
            "address_line1": "测试街道 123 号",
            "city": "测试城市",
            "country": "China",
            "links": [{
                "link_doctype": "Customer",
                "link_name": customer.name
            }]
        }).insert()

        # 4. 创建销售订单（带 Amazon 订单号字段）
        sales_order = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": customer.name,
            "amazon_order_id": "AMZ123456789",  # 假设你有这个自定义字段
            "delivery_date": frappe.utils.nowdate(),
            "items": [{
                "item_code": item.item_code,
                "qty": 1,
                "schedule_date": frappe.utils.nowdate()
            }]
        }).insert()

        # 5. 创建发货单
        delivery_note = frappe.get_doc({
            "doctype": "Delivery Note",
            "customer": customer.name,
            "posting_date": frappe.utils.nowdate(),
            "items": [{
                "item_code": item.item_code,
                "qty": 1,
                "against_sales_order": sales_order.name
            }],
            "shipping_address_name": address.name
        }).insert()

        # 6. 调用你的导出 API
        result = export_delivery_notes_to_csv(delivery_note.name)

        # 7. 验证导出结果
        self.assertIn("file_url", result["message"])
        print("CSV 文件 URL:", result["message"]["file_url"])

        # ✅ 测试成功：已生成文件并包含 file_url

    def tearDown(self):
        # 可选：测试后清理数据库
        frappe.db.rollback()