import frappe
from frappe.utils import flt
from inventory_management_extension.inventory_management_extension.utils import (
    create_barcode_tracker,
    update_batch_tracker,
    get_pick_list,
    add_packing_weights_to_delivery_note,
    reverse_barcode_transactions_for_doc,
    get_uom_conversion_factor,
    resolve_sales_order_item,
)

def before_validate(doc, method=None):
    """
    Delivery Note rows created from a Pick List must keep the UOM ordered on the
    Sales Order Item (the Sales Order child table). This runs before ERPNext
    derives `stock_qty` from `qty` * `conversion_factor`, so both stay consistent.
    """
    sync_item_uom_with_sales_order(doc)


def _resolve_delivery_item_sales_order_item(item):
    """Sales Order Item (child table) row behind a Delivery Note row."""
    pick_list_item = item.get("pick_list_item")
    if pick_list_item:
        pl_item = frappe.db.get_value(
            "Pick List Item",
            pick_list_item,
            ["parent", "sales_order", "sales_order_item"],
            as_dict=True,
        )
        if pl_item:
            if pl_item.sales_order_item:
                so_item = resolve_sales_order_item(
                    item.item_code, pl_item.sales_order, pl_item.sales_order_item
                )
                if so_item:
                    return so_item

            # Fall back to the Sales Order linked on the Pick List itself (covers
            # pick lists whose location rows predate the Sales Order linkage).
            pick_list_so = frappe.db.get_value("Pick List", pl_item.parent, "custom_sales_order")
            if pick_list_so:
                so_item = resolve_sales_order_item(item.item_code, pick_list_so)
                if so_item:
                    return so_item

    if item.get("so_detail"):
        so_item = resolve_sales_order_item(item.item_code, sales_order_item=item.so_detail)
        if so_item:
            return so_item

    if item.get("against_sales_order"):
        return resolve_sales_order_item(item.item_code, item.against_sales_order)

    return None


def sync_item_uom_with_sales_order(doc):
    """Re-express Delivery Note Item qty in the ordered UOM of the Sales Order."""
    for item in doc.get("items") or []:
        so_item = _resolve_delivery_item_sales_order_item(item)
        if not so_item or not so_item.get("uom"):
            continue

        stock_uom = so_item.get("stock_uom") or frappe.db.get_value(
            "Item", item.item_code, "stock_uom"
        )
        cf = flt(so_item.get("conversion_factor")) or get_uom_conversion_factor(
            item.item_code, so_item.get("uom"), stock_uom
        )
        cf = cf or 1.0

        if item.get("uom") == so_item.get("uom"):
            # Already in the ordered UOM (mapped from the Sales Order Item or from
            # a fixed up Pick List row): only make the factor / stock qty match.
            item.conversion_factor = cf
            item.stock_uom = stock_uom
            item.stock_qty = flt(item.get("qty")) * cf
            continue

        # A different UOM: re-express the very same quantity in the ordered UOM
        # so partly delivered rows keep their pending qty.
        existing_cf = flt(item.get("conversion_factor"))
        pending_stock = flt(item.get("qty")) * (existing_cf or 1.0)
        if not pending_stock:
            continue

        item.uom = so_item.get("uom")
        item.stock_uom = stock_uom
        item.conversion_factor = cf
        item.qty = flt(pending_stock / cf, item.precision("qty"))
        item.stock_qty = flt(item.get("qty")) * cf


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
        add_packing_weights_to_delivery_note(doc)
    else:
        pick_list_doc = get_pick_list(doc)
        if pick_list_doc:
            doc.customer = pick_list_doc.customer


def on_cancel(doc, method=None):
    """
    Reverse barcode effects when a Delivery Note is cancelled.
    Barcodes marked as sold from the Pick List for this DN will be reopened.
    """
    reverse_barcode_transactions_for_doc(doc)
    