import frappe
from inventory_management_extension.inventory_management_extension.utils import create_barcode_tracker, update_batch_tracker, get_pick_list

def before_submit(doc, method=None):
    update_batch_tracker(doc)
    
def update_customer(doc):
    pick_list_doc = get_pick_list(doc)
    doc.customer = pick_list_doc.customer if pick_list_doc else None
    doc.taxes_and_charges = get_taxes_charges(doc)
    
def get_taxes_charges(doc):
    taxes_charges = frappe.get_all("Sales Taxes and Charges Template", filters={"is_default":1})
    if taxes_charges:
        return taxes_charges[0].name
    return None
    
def before_save(doc, method=None):
    if doc.is_new():
        update_customer(doc)
    else:
        pick_list_doc = get_pick_list(doc)
        if pick_list_doc:
            doc.customer = pick_list_doc.customer
    