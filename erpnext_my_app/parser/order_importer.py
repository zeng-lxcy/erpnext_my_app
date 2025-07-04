import frappe
import importlib
from erpnext_my_app.parser.utils import *

logger = frappe.logger("erpnext_my_app")

class OrderImporter:
    def __init__(self, platform: str):
		# 根据仓库名称查找仓库
        #self.warehouse = frappe.get_doc("Warehouse", WAREHOUSE_NAME_DEFAULT)
        self.warehouse = WAREHOUSE_NAME_DEFAULT
        self.platform = platform
        logger.error(f"OrderImporter initialized for platform: {self.platform} with warehouse: {self.warehouse}")

    def import_orders(self, file_url: str):
        # 根据电商平台创建对应的订单解析器
        parser_module = f"erpnext_my_app.parser.{self.platform}"
        parser_class_name = f"{self.platform.capitalize()}OrderParser"
        parser_module = importlib.import_module(parser_module)
        parser_class = getattr(parser_module, parser_class_name)
        parser = parser_class(file_url)
        orders = parser.parse()
        self.orders_count = len(orders)

        #logger.error(f"orders parser has done: {len(orders)} orders found.")
		
        # 将文件中的销售订单同步到ERPNext
        created_orders = []
        for order_data in orders:
            so = self._create_sales_order(order_data)
            if so:
                created_orders.append(so.name)
        return created_orders

    def _create_sales_order(self, order_data):
        customer_info = order_data["customer"]
        items = order_data["items"]
        shipping_address_info = order_data.get("shipping_address")
        order_id = order_data["order_id"]
        transaction_date = order_data.get("transaction_date")
        delivery_date = order_data.get("delivery_date")
		
        # 检查订单是否已经存在或者找不到商品（有可能通过sku找不到对应商品）
        existing_so = frappe.db.exists("Sales Order", {
            "amazon_order_id": order_id,
            "docstatus": 1
        })

        if existing_so or len(items) <= 0:
            logger.error(f"Amazon order: {order_id} already exists. [Order ID:{existing_so}] or no items[{len(items)}] found.")
            return None
		
        # 创建客户
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": customer_info.get("name"),
            "customer_group": customer_info.get("group"),
			"customer_type": "Company" if customer_info.get("company") != "" else "Individual",
            "territory": TERRITORY_DEFAULT,
            "custom_phone": customer_info.get("phone")
        })
        customer.flags.ignore_mandatory = True
        customer.insert(ignore_if_duplicate=True)
		
        # 创建客户地址
        shipping_address = frappe.get_doc({
            "doctype": "Address",
            "address_title": customer.name + " - Shipping",
            "address_type": "Shipping",
            "pincode": shipping_address_info.get("pincode", ""),
            "address_line1": shipping_address_info.get("address_line1"),
            "address_line2": shipping_address_info.get("address_line2"),
            "city": shipping_address_info.get("city"),
            "state": get_state_name_from_pincode(
                country_code=shipping_address_info.get("country"),
                postal_code=shipping_address_info.get("pincode"),
                state=shipping_address_info.get("state")
            ),
            "country": "Japan",
            "phone": customer_info.get("phone"),
            "email_id": customer_info.get("email"),
			"links": [{"link_doctype": "Customer", "link_name": customer.name}]
        })
        #shipping_address.append("links", {"link_doctype": "Customer", "link_name": customer.name})
        shipping_address.flags.ignore_mandatory = True
        shipping_address.insert(ignore_if_duplicate=True)
		
        # 创建客户联系人
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": customer_info.get("recipient", customer_info.get("name")),
            "email_id": customer_info.get("email"),
            "phone": customer_info.get("phone"),
            "links": [{"link_doctype": "Customer", "link_name": customer.name}]
        })
        contact.flags.ignore_mandatory = True
        contact.insert(ignore_if_duplicate=True)

        # 遍历商品列表，为其设置仓库
        #for item in items:
        #    item["warehouse"] = self.warehouse
        # 创建销售订单
        so_data = {
            "doctype": "Sales Order",
			"amazon_order_id": order_id,
            "customer": customer.name,
            "transaction_date": transaction_date,
            "delivery_date": delivery_date,
            "items": items,
            "company": COMPANY_NAME_DEFAULT,
            "territory": TERRITORY_DEFAULT,
            "customer_address": shipping_address.name,
			"shipping_address": shipping_address.name,
            "contact_person": contact.name,
			"currency": "JPY"
			#"set_warehouse": self.warehouse
        }
        so = frappe.get_doc(so_data)
        so.insert()
        so.submit()
        return so

def get_state_name_from_pincode(country_code=None, postal_code=None, state=None):
	if not all((country_code, postal_code)):
		return state

	def get_first_three_digits(value):
		if isinstance(value, str):
			if len(value.strip()) == 6 and value.strip().isdigit():
				return int(value[:3])
		elif isinstance(value, int):
			if len(str(value)) == 6:
				return int(str(value)[:3])

	if "india_compliance" in frappe.get_installed_apps() and country_code.lower() == "in":
		from india_compliance.gst_india.constants import STATE_PINCODE_MAPPING

		first_three_digits = get_first_three_digits(postal_code)

		if first_three_digits:
			state_name = ""
			for _state, _range in STATE_PINCODE_MAPPING.items():
				if isinstance(_range[0], tuple):
					for c_range in _range:
						lower_range, upper_range = c_range
						if lower_range <= first_three_digits <= upper_range:
							state_name = _state
							if state and state[0].lower() == _state[0].lower():
								return _state
				else:
					lower_range, upper_range = _range
					if lower_range <= first_three_digits <= upper_range:
						state_name = _state
						if state and state[0].lower() == _state[0].lower():
							return _state
			if state_name:
				return state_name

	return state
