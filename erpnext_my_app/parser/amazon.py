import csv
import frappe
from io import StringIO
from frappe.utils import cint, flt # 假设这些工具函数可用
from frappe.utils.file_manager import get_file # 正确的导入路径

class AmazonOrderParser:
    def __init__(self, file_url): # 接受文件URL
        self.file_url = file_url
        self.content = self._fetch_content_from_file_doc() # 调用方法获取内容

    def _fetch_content_from_file_doc(self):
        """Fetches and decodes content from a file document using frappe.utils.file_manager.get_file."""
        try:
            # 使用 get_file 函数获取文件文档
            # get_file 函数返回一个包含文件内容的字典，例如 {"content": b"..."}
            file_doc = get_file(self.file_url)
            
            # 检查 file_doc 是否有效且包含内容
            if file_doc and file_doc.get("content") is not None:
                return file_doc.get("content").decode("shift_jis")
            else:
                print(f"Warning: No content or invalid file document found for URL: {self.file_url}")
                return "" # 如果没有内容，返回空字符串
        except Exception as e:
            # 捕获在获取或解码文件时可能发生的任何错误
            print(f"Error fetching or decoding file from {self.file_url}: {e}")
            return "" # 发生错误时返回空字符串

    def parse(self):
        # StringIO(self.content) 可以处理空字符串，如果 _fetch_content_from_file_doc 返回空，这里也能正常运行
        reader = csv.DictReader(StringIO(self.content), delimiter='\t')
        raw_orders = {}
        for row in reader:
            order_id = row.get("order-id")
            if not order_id:
                continue # 如果没有 order-id，跳过这一行
            raw_orders.setdefault(order_id, []).append(row)

        parsed_orders = []
        for order_id, rows in raw_orders.items():
            if not rows: # 理论上不会发生，因为只有有 order_id 的行才会被添加
                continue

            first_row = rows[0]

            items = []
            for row in rows:
                # 在数据库根据商品 SKU 或 ASIN 查找商品编码
                item_code = frappe.db.get_value(
                    "Item",
                    filters={"custom_amazon_sku": ["like", f"%{row.get('sku')}%"]},
                    fieldname="item_code",
                )
                if item_code:
                    item_name = frappe.db.get_value(
                        "Item",
                        filters={"item_code": item_code},
                        fieldname="item_name",
                    )
                    items.append({
                        "item_code": item_code, # 商品代码
                        "description": row.get("sku") or "", # 商品 SKU
                        "item_name": item_name,
                        "qty": cint(row.get("quantity-purchased", 1)), # 购买数量，转换为整数
                        "rate": flt(row.get("item-price", 0)) or 0, # 商品单价，转换为浮点数
						#"warehouse": WAREHOUSE_DEFAULT, # 默认仓库
                        "stock_uom": "Nos",
						"conversion_factor": 1.0
                    })
            
            order = {
                "order_id": order_id,   #亚马逊订单号
                "transaction_date": first_row.get("purchase-date"), # 交易日期
                "delivery_date": first_row.get("promise-date"), # 交货日期
                "items": items, # 订单包含的商品列表
                "customer": {
                    "name": first_row.get("buyer-name", ""), # 买家姓名
                    "recipient": first_row.get("recipient-name", ""), # 收件人姓名
                    "company": first_row.get("buyer-company-name", ""), # 买家公司名称
                    "email": first_row.get("buyer-email") or f"{order_id}@amazon", # 买家邮箱
                    "phone": first_row.get("buyer-phone-number", ""), # 买家电话
                    "group": "亚马逊" if first_row.get("default-ship-from-address-name", "龍翔産業株式会社") == "龍翔産業株式会社" else "亚马逊 - Amanex",
                },
                "shipping_address": {
                    "pincode": first_row.get("ship-postal-code", ""), # 邮政编码
                    "country": first_row.get("ship-country", ""), # 国家
                    "state": first_row.get("ship-state", ""), # 省/州
                    "city": first_row.get("ship-city", ""), # 城市
                    "address_line1": first_row.get("ship-address-1", "") + first_row.get("ship-address-2", ""), # 地址行1
                    "address_line2": first_row.get("ship-address-3", ""), # 地址行2
                }
            }
            parsed_orders.append(order)
        return parsed_orders