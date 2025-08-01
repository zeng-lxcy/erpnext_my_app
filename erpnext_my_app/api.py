import csv
import frappe
from io import StringIO
import json
from frappe import _
from frappe.utils import nowdate
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

def export_delivery_notes_to_csv_task(sale_order_ids, carrier: str = "upack", ignore_pending_orders: bool = True, user: str = "Administrator"):
    """
    sale_order_ids: 逗号分隔的 Sales Order ID 字符串
    """

    def safe_date_field(doc, fieldname):
        val = doc.get(fieldname)
        return val.strftime("%Y%m%d") if val else ""

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
            "着店コード", "荷送人コード","荷送担当者",
            "個数", "才数", "重量", "輸送商品１", "輸送商品２", "品名記事１", "品名記事２", "品名記事３", "品名記事４", "品名記事５", "品名記事６",
            "配達指定日", "必着区分", "お客様管理番号", "元払区分", "保険金額", "出荷日付", "登録日付"
        ])
    else:
        writer = csv.writer(output)
        writer.writerow([
            "发货ID", "亚马逊订单号",
            "客户名称", "客户电话", "收货人名称", "收货人电话",
            "收货地址明细", "收货城市", "收货省份", "收货邮编",
            "商品名称", "商品数量",
            "发货名称", "发货电话",
            "发货地址明细", "发货城市", "发货省份", "发货邮编",
            "指定配送日期", "指定配送时间"
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
                "is_return": 0,  # ✅ 排除退货
                "status": ["not in", ["Return", "Return Issued"]],  # 排除退货和已发货的状态
                "name": ["in", parent_names]
            },
            pluck="name"
        )
        
        if not dn_names and ignore_pending_orders:
            logger.error(f"export_delivery_notes_to_csv: No Delivery Notes found for Sales Order {so_id}.")
            errors.append(f"销售订单没有关联的发货单: {so_id}<br>")
            continue

        
        item_names = ""
        item_counts = 0
        item_names_list = []
        customer_name = ""
        customer_phone = ""
        contact = ""
        shipping_address_name = so.shipping_address_name or so.customer_address
        shipping_address = frappe.get_doc("Address", shipping_address_name)
        company = frappe.get_doc("Company", so.company)
        amazon_order_id = so.amazon_order_id or ""
        now = nowdate().replace("-", "") 
        delivery_date = so.delivery_date.strftime("%Y%m%d")
        my_delivery_date = safe_date_field(so, "my_delivery_date")  # 获取自定义的交货日期字段
        #delivery_date = delivery_date if delivery_date >= now else now  # 确保交货日期不早于今天
        delivery_date = now
        
        count += 1
        if dn_names:
            for dn_name in dn_names:
                dn = frappe.get_doc("Delivery Note", dn_name)
                # 忽略未提交的发货单
                if dn.docstatus != 1:
                    errors.append(f"忽略非提交状态的出货单：{dn_name}<br>")
                    continue
                #for field, value in dn.as_dict().items():
                #    print(f"{field}: {value}")

                customer_name = frappe.db.get_value("Customer", dn.customer, "customer_name") or ""
                customer_phone = frappe.db.get_value("Customer", dn.customer, "mobile_no") or ""
                contact = frappe.db.get_value("Contact", dn.contact_person, "first_name") or customer_name


                # 如果是线下客户群组的订单，则联系人不填 
                if so.customer_group == "线下":
                    contact = ""
                    
                # 获取商品名称和数量
                item_names = ""
                item_counts = 0
                item_names_list = []
                for item in dn.get("items", []):
                    item_names_list.append(item.item_name)
                    item_names = item_names + " " + item.item_name
                    item_counts = item_counts  + item.qty
                if len(item_names_list) < 6:
                    item_names_list.extend([""] * (6 - len(item_names_list)))  # 填充到 6 个空位
                item_names_list[3] = "われもの注意"
                item_names_list[4] = dn.name  # 将发货单名称放在第五个位置
                item_names_list[5] = amazon_order_id  # 将亚马逊订单号放在第六个位置

                if carrier == "fukutsu":
                    writer.writerow([
                        "", shipping_address.get_formatted("phone") or customer_phone or "0896-22-4988",
                        shipping_address.get_formatted("address_line1"), shipping_address.get_formatted("city"), shipping_address.get_formatted("state"), customer_name, contact, shipping_address.get_formatted("pincode"), 0, 
                        "", "1896224988", "",
                        int(item_counts), "", "", "", "", item_names_list[0], item_names_list[1], item_names_list[2], item_names_list[3], item_names_list[4], item_names_list[5],
                        my_delivery_date, "", "", 1, 0, int(delivery_date), ""
                    ])
                else:
                    writer.writerow([
                        dn.name, amazon_order_id,
                        customer_name, customer_phone, contact, shipping_address.get_formatted("phone") or "0896-22-4988",
                        shipping_address.get_formatted("address_line1"), shipping_address.get_formatted("city"), shipping_address.get_formatted("state"), shipping_address.get_formatted("pincode"),
                        item_names, int(item_counts),
                        company.get_formatted("company_name"), "0896-22-4988",
                        "津根2840", "四国中央市", "爱媛县", "799-0721",
                        my_delivery_date, ""
                    ])

        else:
            # 如果没有找到发货单，则将订单中的所有商品作为一个包裹来打印面单
            customer_name = frappe.db.get_value("Customer", so.customer, "customer_name") or ""
            customer_phone = frappe.db.get_value("Customer", so.customer, "mobile_no") or ""
            contact = frappe.db.get_value("Contact", so.contact_person, "first_name") or customer_name

            # 如果是线下客户群组的订单，则联系人不填 
            if so.customer_group == "线下":
                contact = ""

            # 获取商品名称和数量
            item_names = ""
            item_counts = 0
            item_names_list = []
            for item in so.items:
                item_names_list.append(item.item_name)
                item_names = item_names + " " + item.item_name
                item_counts = item_counts  + item.qty
            if len(item_names_list) < 6:
                item_names_list.extend([""] * (6 - len(item_names_list)))  # 填充到 6 个空位
                item_names_list[5] = amazon_order_id  # 将亚马逊订单号放在第六个位置

            if carrier == "fukutsu":
                writer.writerow([
                    "", shipping_address.get_formatted("phone") or customer_phone or "0896-22-4988",
                    shipping_address.get_formatted("address_line1"), shipping_address.get_formatted("city"), shipping_address.get_formatted("state"), customer_name, contact, shipping_address.get_formatted("pincode"), 0, 
                    "", "1896224988", "",
                    int(item_counts), "", "", "", "", item_names_list[0], item_names_list[1], item_names_list[2], item_names_list[3], item_names_list[4], item_names_list[5],
                    my_delivery_date, "", "", 1, 0, int(delivery_date), ""
                ])
            else:
                writer.writerow([
                    "", amazon_order_id,
                    customer_name, customer_phone, contact, shipping_address.get_formatted("phone") or "0896-22-4988",
                    shipping_address.get_formatted("address_line1"), shipping_address.get_formatted("city"), shipping_address.get_formatted("state"), shipping_address.get_formatted("pincode"),
                    item_names, int(item_counts),
                    company.get_formatted("company_name"), "0896-22-4988",
                    "津根2840", "四国中央市", "爱媛县", "799-0721",
                    my_delivery_date, ""
                ])

    # 保存为 Frappe 文件
    filename = "delivery_export.csv"
    file_content = output.getvalue()
    #print(file_content)  # 读取并解码为字符串打印
    output.close()

    file_doc = None
    if carrier == "fukutsu":
        file_doc = save_file(filename, file_content.encode("cp932", errors="replace"), None, "", is_private=0)
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
                    "is_return": 0,  # ✅ 排除退货
                    "status": ["not in", ["Return", "Return Issued"]],  # 排除退货和已发货的状态
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
def export_delivery_notes_to_csv(sale_order_ids, carrier: str = "upack", ignore_pending_orders: bool = True):
    user = frappe.session.user
    enqueue(
        method=export_delivery_notes_to_csv_task,
        queue='default',
        timeout=600,
        sale_order_ids=sale_order_ids,
        carrier=carrier,
        ignore_pending_orders=ignore_pending_orders,
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

