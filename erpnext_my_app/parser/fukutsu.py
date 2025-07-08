import csv
from io import StringIO
import frappe
from frappe.utils import getdate, nowdate # 假设这些工具函数可用
from frappe.utils.file_manager import get_file # 正确的导入路径

logger = frappe.logger("erpnext_my_app")

class FukutsuParser:
    def __init__(self, file_url): # 接受文件URL
        self.file_url = file_url
        self.content = self._fetch_content_from_file_doc().lstrip("\ufeff") # 调用方法获取内容

    def _fetch_content_from_file_doc(self):
        """Fetch Shift_JIS content from attached File DocType (self.file_url)."""
        try:
            file_path, file_content = get_file(self.file_url)

            if isinstance(file_content, bytes):
                # 明确按 Shift_JIS 解码（推荐使用 cp932）
                return file_content.decode("cp932", errors="replace")
            elif isinstance(file_content, str):
                return file_content  # 已是字符串，直接返回
            else:
                logger.error(f"FukutsuParser: Unexpected file content type: {type(file_content)} from {self.file_url}")
                return ""

        except Exception as e:
            logger.error(f"FukutsuParser: Error fetching or decoding file from {self.file_url}: {e}")
            return ""


    def parse(self):
        # StringIO(self.content) 可以处理空字符串，如果 _fetch_content_from_file_doc 返回空，这里也能正常运行
        reader = csv.DictReader(StringIO(self.content), delimiter=',')
        raw_orders = {}
        for row in reader:
            order_id = row.get("品名記事１").lstrip("'")
            if not order_id:
                logger.error("FukutsuParser: Missing order-id in row, skipping.")
                continue # 如果没有 order-id，跳过这一行
            raw_orders.setdefault(order_id, []).append(row)

        parsed_orders = []
        for order_id, rows in raw_orders.items():
            if not rows: # 理论上不会发生，因为只有有 order_id 的行才会被添加
                continue

            first_row = rows[0]
            order = {
                "delivery_note_id": order_id,   #销售出货ID
                "amazon_order_id": first_row.get("品名記事２", "").lstrip("'"), # 亚马逊订单ID
                "tracking_no": first_row.get("送り状番号", ""), # 追踪号码
                "carrier": "fukutsu", # 物流公司
                "shipping_date": getdate(first_row.get("出荷日", nowdate())) # 发货日期
            }
            parsed_orders.append(order)
        return parsed_orders