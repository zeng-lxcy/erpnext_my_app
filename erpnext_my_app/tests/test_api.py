import frappe
from frappe.tests.utils import FrappeTestCase

class TestExportDeliveryNotesToCsv(FrappeTestCase):
    def test_export_delivery_notes_to_csv(self):
        frappe.set_user("Administrator")

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

        # 4. 创建销售订单（确保字段 amazon_order_id 存在）
        sales_order = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": customer.name,
            "delivery_date": frappe.utils.nowdate(),
            "amazon_order_id": "AMZ123456789",  # 确保有此字段
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

        # 6. 调用 API（因为是 whitelist 的函数）
        result = frappe.call("erpnext_my_app.api.export_delivery_notes_to_csv", delivery_note.name)

        # 7. 验证导出结果
        self.assertIn("file_url", result["message"])
        print("✅ CSV 文件已生成：", result["message"]["file_url"])

    def tearDown(self):
        # 回滚所有更改
        frappe.db.rollback()
