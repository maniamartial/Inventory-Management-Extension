import frappe
from inventory_management_extension.inventory_management_extension.utils import (
    update_batch_tracker,
    reverse_barcode_transactions_for_doc,
)


def before_submit(doc, method=None):
    """
    A pack barcode is only flagged as `sold` when stock actually leaves the
    warehouse: on Delivery Note submit, or on a Sales Invoice submit that has
    "Update Stock" ticked. An accounts-only invoice does not consume packs.
    """
    if not doc.get("update_stock"):
        return

    update_batch_tracker(doc)


def on_cancel(doc, method=None):
    """
    Reopen the pack barcodes this invoice marked as sold. A barcode that another
    submitted document still holds stays sold (see
    `reverse_barcode_transactions_for_doc`).
    """
    reverse_barcode_transactions_for_doc(doc)
