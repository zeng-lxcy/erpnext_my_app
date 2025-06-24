import csv
import frappe
import _osx_support
from frappe.utils.file_manager import save_file
from frappe.utils import get_site_path
from frappe.contacts.doctype.address.address import get_address_display
from io import StringIO

@frappe.whitelist()
def hello():
    return {"message": "Hello, World!"}

@frappe.whitelist()
def export_delivery_notes_to_csv(delivery_note_ids):
    """
    delivery_note_ids: 逗号分隔的 Delivery Note ID 字符串
    """

    if isinstance(delivery_note_ids, str):
        delivery_note_ids = delivery_note_ids.split(",")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "客户名称", "客户电话", "发货地址", 
        "商品名称", "商品数量", "亚马逊订单号"
    ])

    for dn_id in delivery_note_ids:
        dn = frappe.get_doc("Delivery Note", dn_id)

        customer_name = dn.customer
        customer_phone = frappe.db.get_value("Customer", dn.customer, "mobile_no") or ""
        shipping_address_name = dn.shipping_address_name
        shipping_address = frappe.get_doc("Address", shipping_address_name).as_dict()
        shipping_address_str = get_address_display(shipping_address)


        amazon_order_id = ""
        if dn.items and dn.items[0].against_sales_order:
            sales_order = frappe.get_doc("Sales Order", dn.items[0].against_sales_order)
            amazon_order_id = sales_order.get("amazon_order_id", "")  # 请替换为你实际存储 Amazon Order ID 的字段

        for item in dn.items:
            writer.writerow([
                customer_name,
                customer_phone,
                shipping_address_str,
                item.item_name,
                item.qty,
                amazon_order_id
            ])

    # 保存为 Frappe 文件
    filename = "delivery_export.csv"
    file_content = output.getvalue()
    output.close()

    file_doc = save_file(filename, file_content, "File", None, is_private=0)
    return { "message" : {"file_url" : file_doc.file_url}}
