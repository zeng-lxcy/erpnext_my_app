import frappe
from frappe.tests.utils import FrappeTestCase

class TestExportDeliveryNotesToCsv(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

        # 确保默认仓库类型存在
        for wt in ["Transit", "Stores", "Raw Material", "Finished Goods", "Scrap"]:
            if not frappe.db.exists("Warehouse Type", wt):
                frappe.get_doc({
                    "doctype": "Warehouse Type",
                    "warehouse_type_name": wt,
                    "name": wt
                }).insert()

        # 确保公司存在
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "abbr": "TC",
                "default_currency": "CNY",  # 必填，按你需要修改
                "country": "China"          # 必填，按你需要修改
            }).insert()


        # 确保默认地址模板存在
        if not frappe.db.exists("Address Template", "China"):
            frappe.get_doc({
                "doctype": "Address Template",
                "country": "China",
                "is_default": 1,
                "name": "China"  # Address Template 的主键是 name，通常等于 country
            }).insert()


        # 顶层 Customer Group
        if not frappe.db.exists("Customer Group", "All Customer Groups"):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": "All Customer Groups",
                "is_group": 1
            }).insert()

        # 子 Customer Group
        if not frappe.db.exists("Customer Group", "Commercial"):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": "Commercial",
                "parent_customer_group": "All Customer Groups",
                "is_group": 0
            }).insert()

        # 顶层 Territory
        if not frappe.db.exists("Territory", "All Territories"):
            frappe.get_doc({
                "doctype": "Territory",
                "territory_name": "All Territories",
                "is_group": 1
            }).insert()

        # 顶层 Item Group
        if not frappe.db.exists("Item Group", "All Item Groups"):
            frappe.get_doc({
                "doctype": "Item Group",
                "item_group_name": "All Item Groups",
                "is_group": 1
            }).insert()

        # UOM
        if not frappe.db.exists("UOM", "Nos"):
            frappe.get_doc({
                "doctype": "UOM",
                "uom_name": "Nos"
            }).insert()

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

        # 4. 创建销售订单
        sales_order = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": customer.name,
            "company": "Test Company",
            "delivery_date": frappe.utils.nowdate(),
            "amazon_order_id": "AMZ123456789",
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

        # 6. 调用 API
        result = frappe.call("erpnext_my_app.api.export_delivery_notes_to_csv", delivery_note.name)

        # 7. 验证导出结果
        self.assertIn("file_url", result["message"])
        print("✅ CSV 文件已生成：", result["message"]["file_url"])

    def tearDown(self):
        # 回滚所有更改
        frappe.db.rollback()
