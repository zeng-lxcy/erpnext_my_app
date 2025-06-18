import frappe
from frappe import _

@frappe.whitelist()
def hello():
    return {"message": "Hello, World!"}
