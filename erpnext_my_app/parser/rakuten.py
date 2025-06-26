import csv
from io import StringIO
from frappe.utils import cint, flt
from frappe.utils.file_manager import get_file # Import get_file

class RakutenOrderParser:
    def __init__(self, file_url): # Change content to file_url
        self.file_url = file_url
        # Fetch content from the file URL using get_file and decode it
        self.content = self._fetch_content_from_file_doc()

    def _fetch_content_from_file_doc(self):
        """Fetches and decodes content from a file document using frappe.utils.file_manager.get_file."""
        try:
            # Use get_file to retrieve the file document
            file_doc = get_file(self.file_url)

            # Check if file_doc is valid and contains content
            if file_doc and file_doc.get("content") is not None:
                # Decode the content from bytes to string.
                # Rakuten CSVs often use Shift_JIS or UTF-8.
                # Assuming UTF-8 without BOM for this example, adjust if needed.
                # If you encounter decoding errors, try 'shift_jis' or 'cp932'.
                return file_doc.get("content").decode("utf-8")
            else:
                print(f"Warning: No content or invalid file document found for URL: {self.file_url}")
                return "" # Return an empty string if no content is found
        except Exception as e:
            # Catch any errors during file fetching or decoding
            print(f"Error fetching or decoding file from {self.file_url}: {e}")
            return "" # Return an empty string on error

    def parse(self):
        # Create a CSV DictReader from the fetched content.
        # Note: Rakuten CSVs often do not use a delimiter like '\t',
        # they are typically comma-separated (default for csv.DictReader).
        # If your Rakuten CSV is tab-separated, you would add delimiter='\t'.
        reader = csv.DictReader(StringIO(self.content))
        raw_orders = {}
        for row in reader:
            # Use "受注番号" (Order Number) as the order_id
            order_id = row.get("受注番号")
            if not order_id:
                continue # Skip rows without an order ID
            raw_orders.setdefault(order_id, []).append(row)

        parsed_orders = []
        for order_id, rows in raw_orders.items():
            if not rows:
                continue # Skip if no rows are grouped under this order_id

            first_row = rows[0]

            items = []
            for row in rows:
                items.append({
                    "custom_amazon_sku": row.get("商品番号") or "RAKUTEN-ITEM", # Item SKU/Code
                    "item_name": row.get("商品名", "")[:140], # Item Name, truncated to 140 chars
                    "qty": cint(row.get("個数", 1)), # Quantity, converted to integer
                    "rate": flt(row.get("単価", 0)) # Unit Price, converted to float
                })

            order = {
                "order_id": order_id,
                "transaction_date": first_row.get("注文日") or None, # Order Date
                "customer": {
                    "name": first_row.get("購入者名", "楽天購入者"), # Buyer Name
                    "email": first_row.get("購入者メールアドレス") or f"{order_id}@rakuten", # Buyer Email
                    "phone": first_row.get("購入者電話番号", "") # Buyer Phone Number
                },
                "items": items, # List of items in the order
                "shipping_address": {
                    "name": first_row.get("宛名", ""), # Recipient Name
                    "pincode": first_row.get("郵便番号", ""), # Postal Code
                    "country": first_row.get("国名", "JP"), # Country Name
                    "state": first_row.get("都道府県", ""), # State/Province
                    "city": first_row.get("市区町村", ""), # City
                    "address_line1": first_row.get("町名・番地", "") # Address Line 1
                }
            }
            parsed_orders.append(order)
        return parsed_orders