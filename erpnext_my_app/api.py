import csv
import frappe
from io import StringIO
import json
from frappe import _
from frappe.utils.background_jobs import enqueue
from frappe.utils.file_manager import save_file
from erpnext_my_app.parser.utils import *
from erpnext_my_app.parser.order_importer import OrderImporter
from erpnext_my_app.parser.delivery_importer import DeliveryImporter

logger = frappe.logger("erpnext_my_app")


@frappe.whitelist()
def hello():
    return {"message": "Hello, World!"}

def import_orders_task(file_url: str, platform: str = "amazon", user: str = "Administrator"):
    logger = frappe.logger("erpnext_my_app")
    importer = OrderImporter(platform)
    orders = importer.import_orders(file_url)
    result = {
            "status": len(importer.errors) > 0 and "error" or "success",
            "errors": importer.errors,
            "platform": platform,
            "order_count": importer.orders_count,
            "imported_count": len(orders)
    }

    # 主动通知客户端
    frappe.publish_realtime(
        event='import_orders_completed',
        message={'result': result},
        user=user
    )

def export_delivery_notes_to_csv_task(sale_order_ids, carrier: str = "upack", user: str = "Administrator"):
    """
    sale_order_ids: 逗号分隔的 Sales Order ID 字符串
    """

    errors = []
    count = 0
    logger = frappe.logger("erpnext_my_app")
    #logger.info(f"Calling export_delivery_notes_to_csv with sale_order_ids: {sale_order_ids}")

    if isinstance(sale_order_ids, str):
        try:
            # 前端有时会把 list 转成 JSON 字符串传过来
            sale_order_ids = json.loads(sale_order_ids)
        except Exception:
            sale_order_ids = sale_order_ids.strip("[]").replace('"', '').split(",")  # 保底 fallback

    output = StringIO()
    writer = None
    if carrier == "fukutsu":
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow([
            "荷受人コード", "電話番号",
            "住所１", "住所２", "住所３", "名前１", "名前２", "郵便番号", "特殊計", 
            "荷送人コード",
            "個数", "才数", "重量", "輸送商品１", "輸送商品２", "品名記事１", "品名記事２", "品名記事３",
            "配達指定日", "お客樣管理番号", "元着区分", "保険金額", "出荷日付", "登録日付"
        ])
    else:
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
        parent_names = frappe.get_all(
            "Delivery Note Item",
            filters={"against_sales_order": so_id},
            pluck="parent",
            distinct=True
        )
        # 第二步：只保留已提交状态的 Delivery Note
        dn_names = frappe.get_all(
            "Delivery Note",
            filters={
                "docstatus": 1,
                "name": ["in", parent_names]
            },
            pluck="name"
        )
        
        if not dn_names:
            logger.error(f"export_delivery_notes_to_csv: No Delivery Notes found for Sales Order {so_id}.")
            errors.append(f"销售订单没有关联的发货单: {so_id}<br>")
            continue

        for dn_name in dn_names:
            dn = frappe.get_doc("Delivery Note", dn_name)
            # 忽略未提交的发货单
            if dn.docstatus != 1:
                errors.append(f"忽略非提交状态的出货单：{dn_name}<br>")
                continue
            #for field, value in dn.as_dict().items():
            #    print(f"{field}: {value}")

            count += 1
            customer_name = frappe.db.get_value("Customer", dn.customer, "customer_name") or ""
            customer_phone = frappe.db.get_value("Customer", dn.customer, "mobile_no") or ""
            contact = frappe.db.get_value("Contact", dn.contact_person, "first_name") or customer_name
            shipping_address_name = so.shipping_address_name or so.customer_address
            shipping_address = frappe.get_doc("Address", shipping_address_name)
            company = frappe.get_doc("Company", so.company)
            amazon_order_id = so.amazon_order_id or ""

            # 获取商品名称和数量
            item_names = ""
            item_counts = 0
            for item in dn.get("items", []):
                item_names = item_names + " " + item.item_name
                item_counts = item_counts  + item.qty
            
            if carrier == "fukutsu":
                writer.writerow([
                    "", shipping_address.get_formatted("phone") or customer_phone or "0896-22-4988",
                    shipping_address.get_formatted("address_line1"), shipping_address.get_formatted("city"), shipping_address.get_formatted("state"), customer_name, contact, shipping_address.get_formatted("pincode"), "", 
                    "'1896224988",
                    item_counts, "", "", item_names, "輸送商品２", dn.name, amazon_order_id, "品名記事３",
                    "", "お客樣管理番号", "元着区分", "保険金額", so.delivery_date, ""
                ])
            else:
                writer.writerow([
                    dn.name, amazon_order_id,
                    customer_name, customer_phone, contact, shipping_address.get_formatted("phone") or "0896-22-4988",
                    shipping_address.get_formatted("address_line1"), shipping_address.get_formatted("city"), shipping_address.get_formatted("state"), shipping_address.get_formatted("pincode"),
                    item_names, item_counts,
                    company.get_formatted("company_name"), "0896-22-4988",
                    "津根2840", "四国中央市", "爱媛县", "799-0721"
                ])

    # 保存为 Frappe 文件
    filename = "delivery_export.csv"
    file_content = output.getvalue()
    #print(file_content)  # 读取并解码为字符串打印
    output.close()

    file_doc = None
    if carrier == "fukutsu":
        file_doc = save_file(filename, file_content.encode("shift_jis", errors="replace"), None, "", is_private=0)
    else:
        # 使用 UTF-8 编码保存文件
        # 由于 CSV 文件可能包含非 ASCII 字符，建议使用 UTF-8 编码
        # 但如果需要兼容某些系统，可以使用 shift_jis 编码
        # 这里暂时使用 shift_jis 编码，后续可以根据实际需求调整
        # 例如：file_doc = save_file(filename, file_content.encode("utf-8"), None, "", is_private=0)
        file_doc = save_file(filename, file_content.encode("utf-8"), None, "", is_private=0)
    result = {
            "status": "success",
            "order_count": len(sale_order_ids),
            "imported_count": count,
            "carrier": carrier,
            "file_url": file_doc.file_url,
            "errors": errors
    }

    # 主动通知客户端
    frappe.publish_realtime(
        event='export_delivery_completed',
        message={'result': result},
        user=user
    )

def import_shipments_from_file_task(file_url: str, carrier: str = "upack", user: str = "Administrator"):
    logger = frappe.logger("erpnext_my_app")
    importer = DeliveryImporter(carrier)
    orders = importer.import_orders(file_url)
    result = {
            "status": len(importer.errors) > 0 and "error" or "success",
            "errors": importer.errors,
            "carrier": carrier,
            "order_count": importer.orders_count,
            "imported_count": len(orders)
    }

    # 主动通知客户端
    frappe.publish_realtime(
        event='import_shipments_completed',
        message={'result': result},
        user=user
    )

def export_shipment_to_csv_task(sale_order_ids, platform: str = "amazon", user: str = "Administrator"):
    """
    sale_order_ids: 逗号分隔的 Sales Order ID 字符串
    """
    logger = frappe.logger("erpnext_my_app")
    #logger.info(f"Calling export_shipment_to_csv with sale_order_ids: {sale_order_ids}")

    errors = []
    count = 0

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
            if not so:
                logger.error(f"export_shipment_to_csv: Sales Order {so_id} not found.")
                errors.append(f"销售订单未找到: {so_id}<br>")
                continue
            if len(so.items) <= 0:
                logger.error(f"export_shipment_to_csv: Sales Order {so_id} has no items.")
                errors.append(f"销售订单没有商品: {so_id}<br>")
                continue

            # 1. 找出关联该销售订单的第一条出货单（一个销售订单可能对应多条销售出货，所以只取一条）
            parent_names = frappe.get_all(
                "Delivery Note Item",
                filters={"against_sales_order": so_id},
                fields=["parent"],
                distinct=True
            )
            # 第二步：只保留已提交状态的 Delivery Note
            dn_names = frappe.get_all(
                "Delivery Note",
                filters={
                    "docstatus": 1,
                    "name": ["in", parent_names]
                },
                pluck="name"
            )
            if not dn_names:
                logger.error(f"export_shipment_to_csv: Delivery Note Item for Sales Order {so_id} not found.")
                errors.append(f"销售订单没有关联的出货单: {so_id}<br>")
                continue  # 如果没有找到出货单，跳过

            delivery_note_id = dn_names[0]  # 取第一条出货单
            # 2. 查找该出货单对应的装运单（一个销售出货可能对应多条装运单，所以只取一条）
            shipment_links = frappe.get_all(
                "Shipment Delivery Note",
                filters={"delivery_note": delivery_note_id},
                fields=["parent"],
                limit=1
            )
            if not shipment_links:
                logger.error(f"export_shipment_to_csv: Shipment link for Delivery Note {delivery_note_id} not found for Sales Order {so_id}.")
                errors.append(f"出货单没有关联的装运单: {delivery_note_id} [销售订单： {so_id}]<br>")
                continue  # 如果没有找到出货单，跳过

            shipment_id = shipment_links[0]["parent"]
            # 3. 获取装运单的详细信息
            shipment_doc = frappe.get_doc("Shipment", shipment_id)
            if not shipment_doc:
                logger.error(f"export_shipment_to_csv: Shipment document {shipment_id} not found for Sales Order {so_id}.") 
                errors.append(f"装运单文档未找到: {shipment_id} [销售订单： {so_id}， 出货单： {delivery_note_id}]<br>")
                continue  # 如果没有找到装运单，跳过
            
            # 4. 将装运单信息输出到文件中
            count += 1
            writer.writerow([
                so.amazon_order_id or "",  # 亚马逊订单号
                so.items[0].additional_notes,  # 商品 ASIN
                sum(parcel.count for parcel in shipment_doc.shipment_parcel),
                shipment_doc.pickup_date or "",  # 出货日期
                get_carrier_code(shipment_doc.carrier),  # 配送業者コード
                "",  # 配送业者名称
                shipment_doc.awb_number or "",  # 查询号码
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
            "order_count": len(sale_order_ids),
            "imported_count": count,
            "platform": platform,
            "file_url": file_doc.file_url,
            "errors": errors
    }

    # 主动通知客户端
    frappe.publish_realtime(
        event='export_shipments_completed',
        message={'result': result},
        user=user
    )


@frappe.whitelist()
def import_orders(file_url: str, platform: str = "amazon"):
    user = frappe.session.user
    enqueue(
        method=import_orders_task,
        queue='default',
        timeout=600,
        file_url=file_url,
        platform=platform,
        user=user
    )
    #logger.error(f"Import orders task queued for user: {user} with file_url: {file_url} and platform: {platform}")
    return {"status": "queued"}

@frappe.whitelist()
def export_delivery_notes_to_csv(sale_order_ids, carrier: str = "upack"):
    user = frappe.session.user
    enqueue(
        method=export_delivery_notes_to_csv_task,
        queue='default',
        timeout=600,
        sale_order_ids=sale_order_ids,
        carrier=carrier,
        user=user
    )
    return {"status": "queued"}

@frappe.whitelist()
def import_shipments_from_file(file_url: str, carrier: str = "upack"):
    user = frappe.session.user
    enqueue(
        method=import_shipments_from_file_task,
        queue='default',
        timeout=600,
        file_url=file_url,
        carrier=carrier,
        user=user
    )
    return {"status": "queued"}

@frappe.whitelist()
def export_shipment_to_csv(sale_order_ids, platform: str = "amazon"):
    user = frappe.session.user
    enqueue(
        method=export_shipment_to_csv_task,
        queue='default',
        timeout=600,
        sale_order_ids=sale_order_ids,
        platform=platform,
        user=user
    )
    return {"status": "queued"}

