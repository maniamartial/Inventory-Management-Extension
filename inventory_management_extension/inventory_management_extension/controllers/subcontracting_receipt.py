import frappe
from .stock_entry import (
    generate_batch_no,
    generate_ean13,
    update_barcode_on_item,
    update_serial_and_batch,
    valiadte_item_has_batch,
)
from inventory_management_extension.inventory_management_extension.utils import (
    create_barcode_tracker,
    mark_barcode_as_sold,
    reverse_barcode_transactions_for_doc,
    validate_batch_barcode_qty_uom,
)


def before_save(doc, method=None):
    """Generate transaction barcodes and batch numbers for accepted (FG) items."""
    for item in doc.items:
        if not valiadte_item_has_batch(item.item_code):
            continue
        if not item.custom_transaction_barcode:
            item.custom_transaction_barcode = generate_ean13()
            update_barcode_on_item(item.item_code, item.custom_transaction_barcode)

    generate_batch_no(doc)
    validate_supplied_batch_barcodes(doc)


def validate_supplied_batch_barcodes(doc):
    """
    Consumed RM rows: Batch Barcode pack qty (stock UOM) must match consumed_qty.
    """
    for rm in doc.get("supplied_items") or []:
        if not rm.custom_batch_barcode:
            continue

        tracker = validate_batch_barcode_qty_uom(
            barcode=rm.custom_batch_barcode,
            item_code=rm.rm_item_code,
            qty=rm.consumed_qty,
            uom=rm.stock_uom,
            stock_uom=rm.stock_uom,
            conversion_factor=rm.conversion_factor or 1,
            stock_qty=rm.consumed_qty,
            context=f"consumed raw material {rm.rm_item_code}",
            require_full_pack=True,
        )

        batch_no = tracker.lot_no if tracker.is_lot else tracker.batch
        if batch_no and not rm.batch_no:
            rm.batch_no = batch_no
            rm.use_serial_batch_fields = 1


def on_submit(doc, method=None):
    """
    - Accepted items (items): create Batch Barcode Trackers.
    - Consumed raw materials (supplied_items): mark picked Batch Barcodes as
      consumed (sold), same idea as Stock Entry source rows.
    """
    validate_supplied_batch_barcodes(doc)

    for rm in doc.get("supplied_items") or []:
        batch_barcode = resolve_supplied_batch_barcode(rm)
        if not batch_barcode:
            continue
        mark_barcode_as_sold(
            batch_barcode,
            doc.doctype,
            doc.name,
            transaction_type="Consumption",
            warehouse=doc.supplier_warehouse,
        )

    for item in doc.items:
        if not item.custom_transaction_barcode:
            continue
        if not item.batch_no:
            continue

        create_barcode_tracker(
            item.item_code,
            item.custom_transaction_barcode,
            item.batch_no,
            item.qty,
            item.warehouse,
            item.custom_barcode_image,
            reference_document_type=doc.doctype,
            reference_document_name=doc.name,
            transaction_type="Created",
            item_row=item,
        )
        update_serial_and_batch(doc, item)


def on_cancel(doc, method=None):
    """
    Reverse barcode effects when a Subcontracting Receipt is cancelled.
    - Created FG barcodes are blocked (sold).
    - Consumed RM barcodes are reopened.
    """
    reverse_barcode_transactions_for_doc(doc)


def resolve_supplied_batch_barcode(rm):
    """
    Resolve Batch Barcode Tracker for a consumed raw-material row.
    Prefers custom_batch_barcode; no transaction-barcode fallback on supplied
    items (those barcodes belong to FG packs, not RM packs).
    """
    if rm.get("custom_batch_barcode"):
        return rm.custom_batch_barcode
    return None
