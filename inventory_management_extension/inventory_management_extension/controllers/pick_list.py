import frappe
from frappe import _

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
        total_qty += qty.qty
    if total_qty > sales_order.total_qty:
        frappe.throw(
            _("Total Picked quantity <b>{0}</b> cannot exceed Sales Order quantity <b>{1}</b>").format(
                total_qty, sales_order.total_qty
            )
        )
        