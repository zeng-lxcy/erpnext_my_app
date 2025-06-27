import requests
import frappe
from frappe.utils import get_site_path
from frappe.tests.utils import FrappeTestCase


class TestImportOrders(FrappeTestCase):
    def setUp(self):
        self.file_url = self.createTestFile("https://ryuetsu.erpnext.com/files/amazon-test.txt")
        
        frappe.set_user("Administrator")

        # 创建价格表
        if not frappe.db.exists("Price List", "Standard Selling"):
            frappe.get_doc({
                "doctype": "Price List",
                "name": "Standard Selling",
                "price_list_name": "Standard Selling",
                "selling": 1,
                "currency": "CNY"
            }).insert()

        # 确保汇率存在
        if not frappe.db.exists("Currency Exchange", {"from_currency": "INR", "to_currency": "CNY"}):
            frappe.get_doc({
                "doctype": "Currency Exchange",
                "from_currency": "INR",
                "to_currency": "CNY",
                "exchange_rate": 0.085,  # 设置一个合理的汇率
                "date": frappe.utils.nowdate()
            }).insert()

        # 确保公司存在
        if not frappe.db.exists("Company", "龍越商事株式会社"):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": "龍越商事株式会社",
                "abbr": "RYUETSU",
                "default_currency": "CNY",  # 必填，按你需要修改
                "country": "China"          # 必填，按你需要修改
            }).insert()
            # 创建地址并关联到公司
            company_address = frappe.get_doc({
                "doctype": "Address",
                "address_title": "龍越商事株式会社 - Shipping",
                "address_type": "Shipping",
                "address_line1": "123 测试路",
                "address_line2": "测试楼 5F",
                "city": "上海",
                "state": "上海市",
                "pincode": "200000",
                "country": "China",
                "links": [{
                    "link_doctype": "Company",
                    "link_name": "龍越商事株式会社"
                }]
            }).insert()
            print("✅ 公司地址已创建：", company_address.name)

        # 确保默认仓库类型存在
        for wt in ["Transit", "Stores", "Raw Material", "Finished Goods", "Scrap"]:
            if not frappe.db.exists("Warehouse Type", wt):
                frappe.get_doc({
                    "doctype": "Warehouse Type",
                    "warehouse_type_name": wt,
                    "name": wt
                }).insert()

        # 这里添加了一个新的仓库类型 "线上天瞳"，用于测试  
        for wt in ["线上天瞳"]:
            if not frappe.db.exists("Warehouse", wt):
                frappe.get_doc({
                    "doctype": "Warehouse",
                    "warehouse_name": wt,
                    "company": company.name,
                    "name": wt
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
        if not frappe.db.exists("Customer Group", "Amazon"):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": "Amazon",
                "parent_customer_group": "All Customer Groups",
                "is_group": 1
            }).insert()
        # 子 Customer Group
        for wt in ["亚马逊 - Amanex", "亚马逊"]:
            if not frappe.db.exists("Customer Group", wt):
                frappe.get_doc({
                    "doctype": "Customer Group",
                    "customer_group_name": wt,
                    "parent_customer_group": "Amazon",
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

        # 商品
        if not frappe.db.exists("Item", "测试商品"):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": "测试商品",
                "item_name": "测试商品",
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "custom_amazon_sku": "rs-55ccc"  # 示例 SKU
            }).insert()

        # UOM
        if not frappe.db.exists("UOM", "Nos"):
            frappe.get_doc({
                "doctype": "UOM",
                "uom_name": "Nos"
            }).insert()
        
        print("✅ 测试环境已准备就绪")

    def fetchFileContent(self, url: str):
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            return resp.content.decode("shift_jis", errors="replace")
        except Exception as e:
            print(f"Error downloading or decoding file: {e}")
            return ""
    
    def createTestFile(self, url):
        # 1. 写入本地 public/files 目录
        file_path = get_site_path("public", "files", "amazon-test.txt")
        with open(file_path, "w", encoding="shift_jis", errors="replace") as f:
            f.write(self.fetchFileContent(url).replace("\ufffd", "?"))

        # 2. 在 File Doctype 中注册该文件
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_url": f"{"amazon-test.txt"}",
            "is_private": 0,
            "attached_to_doctype": None,
            "attached_to_name": None,
        })
        file_doc.insert(ignore_permissions=True)
        print("✅ 测试文件已创建：", file_path)

        # 3. 返回可用于 get_file 的 file_url
        return file_path

    def test_import_orders(self):
        print("开始导入亚马逊订单...")
        # 1. 调用 API
        result = frappe.call("erpnext_my_app.api.import_orders", self.file_url, platform="amazon")
        expected_result = {
                "status": "success",
                "platform": "amazon",
                "imported_count": 12,
        }

        # 2. 验证结果
        self.assertEqual(expected_result, result)
        print("亚马逊订单成功导入数：", result["imported_count"])

    def tearDown(self):
        # 回滚所有更改
        frappe.db.rollback()


class TestExportDeliveryNotesToCsv(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

        # 确保地址模板存在
        if not frappe.db.exists("Address Template", "Default"):
            frappe.get_doc({
                "doctype": "Address Template",
                "name": "Default",
                "is_default": 1,
                "country": "Japan",  # 改成你使用的国家
                "template": """
                    {{ address_line1 }}
                    {{ address_line2 }}
                    {{ city }} {{ state }}
                    {{ pincode }}
                    {{ country }}
                """.strip()
            }).insert(ignore_if_duplicate=True)

        # 创建价格表
        if not frappe.db.exists("Price List", "Standard Selling"):
            frappe.get_doc({
                "doctype": "Price List",
                "name": "Standard Selling",
                "price_list_name": "Standard Selling",
                "selling": 1,
                "currency": "CNY"
            }).insert()

        # 确保汇率存在
        if not frappe.db.exists("Currency Exchange", {"from_currency": "INR", "to_currency": "CNY"}):
            frappe.get_doc({
                "doctype": "Currency Exchange",
                "from_currency": "INR",
                "to_currency": "CNY",
                "exchange_rate": 0.085,  # 设置一个合理的汇率
                "date": frappe.utils.nowdate()
            }).insert()

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
            # 创建地址并关联到公司
            company_address = frappe.get_doc({
                "doctype": "Address",
                "address_title": "Test Company - Shipping",
                "address_type": "Shipping",
                "address_line1": "123 测试路",
                "address_line2": "测试楼 5F",
                "city": "上海",
                "state": "上海市",
                "pincode": "200000",
                "country": "China",
                "links": [{
                    "link_doctype": "Company",
                    "link_name": "Test Company"
                }]
            }).insert()
            print("✅ 公司地址已创建：", company_address.name)

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
            "selling_price_list": "Standard Selling",
            "price_list_currency": "CNY",
            "plc_conversion_rate": 1.0,  # 直接设定为 1.0
            "items": [{
                "item_code": item.item_code,
                "qty": 1,
                "schedule_date": frappe.utils.nowdate()
            }]
        }).insert()
        sales_order_item_name = sales_order.items[0].name

        # 5. 创建发货单
        delivery_note = frappe.get_doc({
            "doctype": "Delivery Note",
            "company": "Test Company",
            "customer": customer.name,
            "posting_date": frappe.utils.nowdate(),
            "items": [{
                "item_code": item.item_code,
                "qty": 1,
                "rate": 100,  # 必须有价格
                "warehouse": "Stores - TC",  # 或你系统中的有效仓库
                "against_sales_order": sales_order.name,
                "against_sales_order_item": sales_order_item_name,
                "so_detail": sales_order_item_name  # 明确指定 Sales Order Item
            }],
            "shipping_address_name": address.name,
            "delivery_date": frappe.utils.nowdate()
        }).insert()

        # 6. 调用 API
        result = frappe.call("erpnext_my_app.api.export_delivery_notes_to_csv", delivery_note.name)
        expected_result = {
                "status": "success",
                "file_url": result["file_url"],
        }
        # 7. 验证导出结果
        self.assertEqual(expected_result, result)
        print("发货 CSV 文件已生成：", result["file_url"])

    def tearDown(self):
        # 回滚所有更改
        frappe.db.rollback()
