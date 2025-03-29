import frappe
from inventory_management_extension.inventory_management_extension.utils import create_barcode_tracker, update_batch_tracker

def before_submit(doc, method=None):
    update_batch_tracker(doc)