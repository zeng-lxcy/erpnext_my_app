import csv
import frappe
from io import StringIO
from frappe.utils.file_manager import save_file
from erpnext_my_app.parser.order_importer import OrderImporter
import json

logger = frappe.logger("erpnext_my_app")

@frappe.whitelist()
def hello():
    return {"message": "Hello, World!"}

@frappe.whitelist()
def import_orders(file_url: str, platform: str = "amazon"):
    importer = OrderImporter(platform)
    orders = importer.import_orders(file_url, platform)
    result = {
            "status": "success",
            "platform": platform,
            "imported_count": len(orders)
    }
    logger.info(f"Imported {len(orders)} orders from {platform} platform.")
    return result

@frappe.whitelist()
def export_delivery_notes_to_csv(sale_order_ids):
    """
    sale_order_ids: 逗号分隔的 Delivery Note ID 字符串
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
            #if dn.status != "Submitted":
            #    continue
            #for field, value in dn.as_dict().items():
            #    print(f"{field}: {value}")

            customer_name = dn.customer
            customer_phone = frappe.db.get_value("Customer", dn.customer, "mobile_no") or ""
            shipping_address_name = so.shipping_address_name or so.customer_address
            shipping_address = frappe.get_doc("Address", shipping_address_name)
            company = frappe.get_doc("Company", so.company)
            amazon_order_id = so.amazon_order_id or ""

            for item in dn.get("items", []):
                writer.writerow([
                    dn.name, amazon_order_id,
                    customer_name, customer_phone, dn.contact_person, dn.contact_mobile,
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
