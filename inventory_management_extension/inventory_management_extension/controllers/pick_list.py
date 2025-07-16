import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.mapper import get_mapped_doc



def before_submit(doc, method=None):
    validate_qty(doc)
    for item in doc.locations:
        missing_fields = []

        if not item.custom_packaging_item:
            missing_fields.append('<span style="color:purple;">Packaging Item</span>')
        if not item.custom_packing_weight or item.custom_packing_weight == 0:
            missing_fields.append('<span style="color:purple;">Packing Weight</span>')
        if not item.custom_gross_weight or item.custom_gross_weight <= 0:
            missing_fields.append('<span style="color:purple;">Gross Weight</span>')

        if missing_fields:
            frappe.throw(
                _("Missing {0} for item <b style='color:black;'>{1}</b>").format(", ".join(missing_fields), item.item_code)
            )
    


def validate_qty(doc):
    total_qty = 0
    sales_order = frappe.get_doc("Sales Order", doc.custom_sales_order)
    if not sales_order:
        frappe.throw(_("Sales Order is not linked."))

    for qty in doc.locations:
        total_qty += flt(qty.qty, 4)  # Or use 4/5 if you need more precision

    if flt(total_qty, 4) > flt(sales_order.total_qty, 4):
        frappe.throw(
            _("Total Picked quantity <b>{0}</b> cannot exceed Sales Order quantity <b>{1}</b>").format(
                total_qty, sales_order.total_qty
            )
        )
        
def before_save(doc, method=None):
    validate_qty(doc)
    calculate_package_weight(doc)
    
def calculate_package_weight(doc):
    # total_weight = 0
    for item in doc.locations:
        item.custom_packaging_item = doc.custom_packaging_item
        item.custom_packing_weight = doc.custom_packing_weight
        item.custom_packaging_itemuom = doc.custom_packaging_itemuom
        item.custom_cubic = doc.custom_cubic * item.custom_barcode_no
        item.custom_gross_weight = (doc.custom_packing_weight * item.custom_barcode_no) + item.qty


@frappe.whitelist()
def picklist_to_invoice(picklist_name):
    picklist = frappe.get_doc("Pick List", picklist_name)

    if not picklist.custom_sales_order:
        frappe.throw(_("No Sales Order linked to Pick List"))

    sales_order = frappe.get_doc("Sales Order", picklist.custom_sales_order)

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = sales_order.customer
    invoice.due_date = frappe.utils.nowdate()
    invoice.custom_sales_order = sales_order.name
    invoice.set_posting_time = 1
    invoice.currency = sales_order.currency
    invoice.conversion_rate = sales_order.conversion_rate
    invoice.selling_price_list = sales_order.selling_price_list
    invoice.price_list_currency = sales_order.price_list_currency
    invoice.plc_conversion_rate = sales_order.plc_conversion_rate

    for loc in picklist.locations:
        so_item = next((item for item in sales_order.items if item.item_code == loc.item_code), None)
        if not so_item:
            continue

        invoice.append("items", {
            "item_code": loc.item_code,
            "qty": loc.qty,
            "uom": so_item.uom,
            "stock_uom": so_item.stock_uom,
            "warehouse": loc.warehouse,
            "rate": so_item.rate,
            "base_rate": so_item.base_rate,
            "batch_no": loc.batch_no,
            "sales_order": sales_order.name,
            "sales_order_item": so_item.name,
            "custom_barcode_no": loc.custom_barcode_no,
            "custom_package_item": loc.custom_packaging_item,
            "custom_package_weight": loc.custom_packing_weight,
            "custom_gross_weight": loc.custom_gross_weight,
            "custom_cubic": loc.custom_cubic,
            "custom_packaging_itemuom": loc.custom_packaging_itemuom,
        })

    invoice.flags.ignore_permissions = True
    invoice.insert()
    return invoice.name
