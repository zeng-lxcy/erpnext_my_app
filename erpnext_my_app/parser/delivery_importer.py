import frappe
import importlib
from frappe.utils import getdate

logger = frappe.logger("erpnext_my_app")

class DeliveryImporter:
    def __init__(self, carrier: str):
        self.carrier = carrier
        self.errors = []
        self.orders_count = 0

    def import_orders(self, file_url: str):
        # 根据快递公司创建对应的快递单解析器
        parser_module = f"erpnext_my_app.parser.{self.carrier}"
        parser_class_name = f"{self.carrier.capitalize()}Parser"
        parser_module = importlib.import_module(parser_module)
        parser_class = getattr(parser_module, parser_class_name)
        parser = parser_class(file_url)
        orders = parser.parse()
        self.orders_count = len(orders)

        #logger.error(f"DeliveryImporter: Delivery parser has done: {len(orders)} records found.")

        # 将快递单号同步到ERPNext
        shippments = []
        for shippment_data in orders:
            s = self._create_shippment(shippment_data)
            if s:
                shippments.append(s.name)
        return shippments

    def _create_shippment(self, shipment_data):
        delivery_note_id = shipment_data.get("delivery_note_id")
        tracking_number = shipment_data.get("tracking_no")
        carrier = shipment_data.get("carrier")
        shipping_date = shipment_data.get("shipping_date")

        # 加载 Delivery Note 文档
        dn = frappe.get_doc("Delivery Note", delivery_note_id)
        
        # 检查发货单是否存在
        if not dn:
            logger.error(f"DeliveryImporter: Delivery Note {delivery_note_id} not found.")
            self.errors.append(f"发货单不存在： {delivery_note_id}<br>")
            return None

        order_id = dn.items[0].against_sales_order if dn.items else None
        # 更新销售订单中的自定义字段“快递单号”
        #so = frappe.get_doc("Sales Order", shipment_data.get("amazon_order_id"))
        so = frappe.get_doc("Sales Order", order_id)
        if so:
            so.custom_tracking_number = f"{tracking_number} ({carrier})"
            so.save()

        # 检查是否已经存在对应发货单的 Shipment
        existing_shipment = frappe.db.exists("Shipment", {
            "delivery_note": delivery_note_id,
            "docstatus": ["!=", 2]  # 不是已取消
        })
        if existing_shipment:
            logger.error(f"DeliveryImporter: Shipment for Delivery Note {delivery_note_id} already exists.")
            self.errors.append(f"发货单对应的装运单已经存在：{delivery_note_id}<br>")
            return None

        # 估算总价值（简单求和）
        total_value = sum([item.amount for item in dn.items])

        #logger.error(f"DeliveryImporter: Creating Shipment for Delivery Note {delivery_note_id} with tracking number {tracking_number}.")
        # 创建 Shipment
        shipment = frappe.get_doc({
            "doctype": "Shipment",
            "delivery_note": delivery_note_id,
            "awb_number": tracking_number,
            "carrier": carrier,
            "shipment_date": getdate(shipping_date),
            "shipment_type": "Goods",  # 发出货物
            "pickup_contact_person": "",
            "pickup_contact_name": "",  # 提货联系人名称
            "pickup_address_name": dn.company_address,
            "pickup_date": getdate(dn.posting_date),
            "pickup_from": dn.posting_time,  # 提货起始时间
            "pickup_to": dn.posting_time,  # 提货截至时间
            "value_of_goods": total_value,
            "delivery_customer": dn.customer,
            "delivery_address_name": dn.shipping_address_name,
            "delivery_contact_name": dn.contact_person,
            "recipient_name": dn.contact_display,
            "description_of_content": "销售出货配送",  # 内容描述，可自定义
        })

        # 添加 Delivery Note 关联
        shipment.append("shipment_delivery_note", {
            "delivery_note": delivery_note_id
        })
        
        # 添加 Shipment Parcel 信息
        for i in dn.items:
            #logger.error(f"DeliveryImporter: Item code {i.item_name}.")
            item = frappe.get_doc("Item", i.item_code)
            if not item:
                logger.error(f"DeliveryImporter: Item {i.item_name} not found.")
                self.errors.append(f"出货单的商品没有找到： {i.item_name}[出货单: {delivery_note_id}]<br>")
                continue
            shipment.append("shipment_parcel", {
                    "description": item.item_name,
                    "qty": i.qty,
                    "weight": item.weight_per_unit <= 0.0 and 1.0 or item.weight_per_unit,  # 如果重量为0，则默认1kg
                    "weight_uom": item.weight_uom or "kg",
                    "length":  10.0,
                    "width":  10.0,
                    "height":  10.0,
                    "dimension_uom": "cm",
            })

        shipment.insert(ignore_permissions=True)
        shipment.submit()
        return shipment
