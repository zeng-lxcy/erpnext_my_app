import csv
import frappe
import _osx_support
from frappe.utils.file_manager import save_file
from frappe.utils import get_site_path
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
        "亚马逊订单号",
        "客户名称", "客户电话",
        "收货地址明细", "收货城市", "收货省份",
        "商品名称", "商品数量",
        "发货名称", "发货电话",
        "发货地址明细", "发货城市", "发货省份"
    ])

    for dn_id in delivery_note_ids:
        dn = frappe.get_doc("Delivery Note", dn_id)

        customer_name = dn.customer
        customer_phone = frappe.db.get_value("Customer", dn.customer, "mobile_no") or ""
        shipping_address_name = dn.shipping_address_name
        shipping_address = frappe.get_doc("Address", shipping_address_name)
        company = frappe.get_doc("Company", dn.company)
        shipping_address_s = frappe.get_all("Address",
            filters={
                "links.link_doctype": "Company",
                "links.address_type": "Shipping",
                "links.link_name": company.name
            },
            limit=1
        )

        amazon_order_id = ""
        if dn.items and dn.items[0].against_sales_order:
            sales_order = frappe.get_doc("Sales Order", dn.items[0].against_sales_order)
            amazon_order_id = sales_order.get("amazon_order_id", "amazon_order_id")

        for item in dn.items:
            writer.writerow([
                amazon_order_id,
                customer_name,
                customer_phone,
                shipping_address.get_formatted("address_line1"),
                shipping_address.get_formatted("city"),
                shipping_address.get_formatted("state"),
                item.item_name,
                item.qty,
                company.get_formatted("company_name"),
                company.get_formatted("phone"),
                shipping_address_s.get_formatted("address_line1"),
                shipping_address_s.get_formatted("city"),
                shipping_address_s.get_formatted("state")
            ])

    # 保存为 Frappe 文件
    filename = "delivery_export.csv"
    file_content = output.getvalue()
    print(file_content)  # 读取并解码为字符串打印
    output.close()

    file_doc = save_file(filename, file_content, None, "", is_private=0)
    return { "message" : {"file_url" : file_doc.file_url}}
