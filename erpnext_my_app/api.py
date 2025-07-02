import csv
import frappe
from io import StringIO
import json
from frappe import _
from frappe.utils.file_manager import save_file
from erpnext_my_app.parser.order_importer import OrderImporter
from erpnext_my_app.parser.delivery_importer import DeliveryImporter

logger = frappe.logger("erpnext_my_app")

def get_carrier_code(carrier):
    carrier_map = {
        "yamato": "YAMATO",
        "sagawa": "SAGAWA",
        "upack": "JapanPost",
        "other": "Other",
        "fedex": "FedEx",
        "dhl": "DHL",
        "ups": "UPS",
        "amazon": "Amazon"
    }

    return carrier_map.get(carrier, "unknown")

def get_shipment_method(carrier):
    carrier_map = {
        "yamato": "ヤマト運輸",
        "sagawa": "佐川急便",
        "upack": "日本郵便",
        "other": "セイノースーパーエクスプレス",
        "fedex": "FedEx",
        "dhl": "DHL",
        "ups": "UPS",
        "amazon": "Amazon配送"
    }

    return carrier_map.get(carrier, "unknown")


@frappe.whitelist()
def hello():
    return {"message": "Hello, World!"}

@frappe.whitelist()
def import_orders(file_url: str, platform: str = "amazon"):
    frappe.logger().warning("Calling import_orders with file_url: {} and platform: {}".format(file_url, platform))

    importer = OrderImporter(platform)
    orders = importer.import_orders(file_url)
    result = {
            "status": "success",
            "platform": platform,
            "imported_count": len(orders)
    }
    logger.info(f"Imported {len(orders)} orders from {platform} platform.")
    return result

@frappe.whitelist()
def export_delivery_notes_to_csv(sale_order_ids, carrier: str = "upack"):
    """
    sale_order_ids: 逗号分隔的 Sales Order ID 字符串
    """

    #logger.info(f"Calling export_delivery_notes_to_csv with sale_order_ids: {sale_order_ids}")

    if isinstance(sale_order_ids, str):
        try:
            # 前端有时会把 list 转成 JSON 字符串传过来
            sale_order_ids = json.loads(sale_order_ids)
        except Exception:
            sale_order_ids = sale_order_ids.strip("[]").replace('"', '').split(",")  # 保底 fallback

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "发货ID", "亚马逊订单号",
        "客户名称", "客户电话", "收货人名称", "收货人电话",
        "收货地址明细", "收货城市", "收货省份", "收货邮编",
        "商品名称", "商品数量",
        "发货名称", "发货电话",
        "发货地址明细", "发货城市", "发货省份", "发货邮编"
    ])

    for so_id in sale_order_ids:
        so = frappe.get_doc("Sales Order", so_id)
        dn_names = frappe.get_all(
            "Delivery Note Item",
            filters={"against_sales_order": so_id},
            pluck="parent"
        )
        for dn_name in dn_names:
            dn = frappe.get_doc("Delivery Note", dn_name)
            # 忽略未提交的发货单
            if dn.docstatus != 1:
                continue
            #for field, value in dn.as_dict().items():
            #    print(f"{field}: {value}")

            customer_name = frappe.db.get_value("Customer", dn.customer, "customer_name") or ""
            customer_phone = frappe.db.get_value("Customer", dn.customer, "mobile_no") or ""
            contact = frappe.db.get_value("Contact", dn.contact_person, "first_name") or customer_name
            shipping_address_name = so.shipping_address_name or so.customer_address
            shipping_address = frappe.get_doc("Address", shipping_address_name)
            company = frappe.get_doc("Company", so.company)
            amazon_order_id = so.amazon_order_id or ""

            for item in dn.get("items", []):
                writer.writerow([
                    dn.name, amazon_order_id,
                    customer_name, customer_phone, contact, shipping_address.get_formatted("phone") or "0896-22-4988",
                    shipping_address.get_formatted("address_line1"), shipping_address.get_formatted("city"), shipping_address.get_formatted("state"), shipping_address.get_formatted("pincode"),
                    item.item_name, item.qty,
                    company.get_formatted("company_name"), "0896-22-4988",
                    "津根2840", "四国中央市", "爱媛县", "799-0721"
                ])

    # 保存为 Frappe 文件
    filename = "delivery_export.csv"
    file_content = output.getvalue()
    #print(file_content)  # 读取并解码为字符串打印
    output.close()

    #file_doc = save_file(filename, file_content.encode("shift_jis", errors="replace"), None, "", is_private=0)
    file_doc = save_file(filename, file_content.encode("utf-8"), None, "", is_private=0)
    result = {
            "status": "success",
            "file_url": file_doc.file_url,
    }
    #logger.info(f"Exported delivery notes to {file_doc.file_url}")
    return result

@frappe.whitelist()
def import_shipments_from_file(file_url: str, carrier: str = "upack"):
    importer = DeliveryImporter(carrier)
    orders = importer.import_orders(file_url)
    result = {
            "status": "success",
            "carrier": carrier,
            "imported_count": len(orders)
    }
    logger.info(f"Imported {len(orders)} orders from {carrier} carrier.")
    return result

@frappe.whitelist()
def export_shipment_to_csv(sale_order_ids, platform: str = "amazon"):
    """
    sale_order_ids: 逗号分隔的 Sales Order ID 字符串
    """

    #logger.info(f"Calling export_shipment_to_csv with sale_order_ids: {sale_order_ids}")

    if isinstance(sale_order_ids, str):
        try:
            # 前端有时会把 list 转成 JSON 字符串传过来
            sale_order_ids = json.loads(sale_order_ids)
        except Exception:
            sale_order_ids = sale_order_ids.strip("[]").replace('"', '').split(",")  # 保底 fallback

    output = StringIO()
    
    if platform == "amazon":
        writer = csv.writer(output, delimiter="\t") # 使用制表符分隔符
        writer.writerow([
            "TemplateType=OrderFulfillment", "Version=2011.1102", "この行はAmazonが使用しますので変更や削除しないでください。",
        ])
        writer.writerow([
            "注文番号", "注文商品番号", "出荷数","出荷日",
            "配送業者コード", "配送業者名", "お問い合わせ伝票番号", "配送方法", "代金引換"
        ])

        for so_id in sale_order_ids:
            so = frappe.get_doc("Sales Order", so_id)
            if not so or len(so.items) == 0:
                continue

            # 1. 找出关联该销售订单的第一条出货单（一个销售订单可能对应多条销售出货，所以只取一条）
            delivery_note_item = frappe.get_all(
                "Delivery Note Item",
                filters={"against_sales_order": so_id},
                fields=["parent"],
                order_by="creation asc",
                limit=1
            )
            if not delivery_note_item:
                continue  # 如果没有找到出货单，跳过

            delivery_note_id = delivery_note_item[0]["parent"]
            # 2. 查找该出货单对应的装运单（一个销售出货可能对应多条装运单，所以只取一条）
            shipment_links = frappe.get_all(
                "Shipment Delivery Note",
                filters={"delivery_note": delivery_note_id},
                fields=["parent"],
                limit=1
            )
            if not shipment_links:
                continue  # 如果没有找到出货单，跳过

            shipment_id = shipment_links[0]["parent"]
            # 3. 获取装运单的详细信息
            shipment_doc = frappe.get_doc("Shipment", shipment_id)
            if not shipment_doc:
                continue  # 如果没有找到装运单，跳过
            
            # 4. 将装运单信息输出到文件中
            writer.writerow([
                so.amazon_order_id or "",  # 亚马逊订单号
                so.items[0].additional_notes,  # 商品 ASIN
                shipment_doc.get("items", [{}])[0].get("qty", 0),  # 出货数量，取第一条商品的数量
                shipment_doc.posting_date or "",  # 出货日期
                get_carrier_code(shipment_doc.carrier),  # 配送業者コード
                "",  # 配送业者名称
                shipment_doc.tracking_number or "",  # 查询号码
                get_shipment_method(shipment_doc.carrier),  # 配送方法
                ""
            ])  # 空行

    # 保存为 Frappe 文件
    filename = "shipment_export.csv"
    file_content = output.getvalue()
    print(file_content)  # 读取并解码为字符串打印
    output.close()

    file_doc = save_file(filename, file_content.encode("shift_jis", errors="replace"), None, "", is_private=0)
    #file_doc = save_file(filename, file_content.encode("utf-8"), None, "", is_private=0)
    result = {
            "status": "success",
            "file_url": file_doc.file_url,
    }
    #logger.info(f"Exported delivery notes to {file_doc.file_url}")
    return result

