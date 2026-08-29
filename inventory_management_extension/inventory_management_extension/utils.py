
import frappe 
from frappe.utils import flt
from frappe import _
from frappe.model.document import Document
from barcode import Code128
from barcode.writer import ImageWriter
import frappe
from frappe.utils.file_manager import save_file
import re
from frappe.utils import flt


def create_barcode_tracker(
    item_code,
    barcode,
    batch,
    qty,
    warehouse,
    barcode_image,
    is_lot=None,
    reference_document_type=None,
    reference_document_name=None,
    transaction_type="Created",
):
    """
    Create a barcode tracker for the given item code, barcode, and batch.
    Adds a transaction history entry. Use transaction_type="Purchased" for
    Purchase Receipt, "Repacked" for Repack target, "Created" for Manufacture
    or Material Receipt, etc.
    """
    image = barcode_image if barcode_image else generate_image_for_barcode(barcode)

    if frappe.db.exists("Batch Barcode Tracker", {"barcode": barcode}):
        frappe.throw("Barcode already exists.")

    barcode_tracker = frappe.get_doc({
        "doctype": "Batch Barcode Tracker",
        "item_code": item_code,
        "barcode": barcode,
        "batch": batch,
        "qty": qty,
        "barcode_image": image,
        "is_lot": is_lot,
        "lot_no": batch if is_lot else None,
        "warehouse": warehouse,
    })

    # Add transaction history entry
    if reference_document_type and reference_document_name:
        barcode_tracker.append("transaction_history", {
            "transaction_type": transaction_type,
            "reference_document_type": reference_document_type,
            "reference_document_name": reference_document_name,
            "warehouse": warehouse,
            "posting_date": frappe.utils.today(),
            "posting_time": frappe.utils.nowtime(),
        })

    barcode_tracker.insert(ignore_permissions=True)
    barcode_tracker.submit()
    frappe.db.commit()

    return barcode_tracker


def _append_barcode_transaction(
    barcode_name: str,
    transaction_type: str,
    reference_document_type: str | None,
    reference_document_name: str | None,
    warehouse: str | None = None,
    from_warehouse: str | None = None,
):
    """Low-level helper to append a transaction row without touching parent docstatus."""
    if not (reference_document_type and reference_document_name):
        return

    txn = frappe.get_doc({
        "doctype": "Batch Barcode Tracker Transaction",
        "parent": barcode_name,
        "parenttype": "Batch Barcode Tracker",
        "parentfield": "transaction_history",
        "transaction_type": transaction_type,
        "reference_document_type": reference_document_type,
        "reference_document_name": reference_document_name,
        "warehouse": warehouse,
        "from_warehouse": from_warehouse,
        "posting_date": frappe.utils.today(),
        "posting_time": frappe.utils.nowtime(),
    })
    txn.insert(ignore_permissions=True)


def mark_barcode_as_sold(
    barcode_name,
    reference_document_type,
    reference_document_name,
    transaction_type="Sold",
    warehouse=None,
):
    """
    Mark a batch barcode tracker as sold and add transaction history entry.
    Use transaction_type e.g. "Sold", "Issue", "Consumption", "Repacked".
    """
    frappe.db.set_value("Batch Barcode Tracker", barcode_name, "sold", 1)

    _append_barcode_transaction(
        barcode_name,
        transaction_type,
        reference_document_type,
        reference_document_name,
        warehouse=warehouse,
    )


def update_barcode_warehouse_and_add_transfer(
    barcode_name,
    to_warehouse,
    from_warehouse,
    reference_document_type,
    reference_document_name,
):
    """
    For Material Transfer: update the Batch Barcode Tracker warehouse and
    record a Transfer transaction. Does not create a new tracker or change sold.
    """
    frappe.db.set_value("Batch Barcode Tracker", barcode_name, "warehouse", to_warehouse)

    _append_barcode_transaction(
        barcode_name,
        "Transfer",
        reference_document_type,
        reference_document_name,
        warehouse=to_warehouse,
        from_warehouse=from_warehouse,
    )


def unmark_barcode_as_sold(
    barcode_name,
    reference_document_type,
    reference_document_name,
    warehouse=None,
):
    """
    Reverse a sold barcode (e.g. on cancellation) and add Reopened transaction.
    """
    current_sold = frappe.db.get_value(
        "Batch Barcode Tracker", barcode_name, "sold"
    )
    if not current_sold:
        return

    frappe.db.set_value("Batch Barcode Tracker", barcode_name, "sold", 0)

    _append_barcode_transaction(
        barcode_name,
        "Reopened",
        reference_document_type,
        reference_document_name,
        warehouse=warehouse,
    )


def reverse_barcode_transactions_for_doc(doc):
    """
    Reverse barcode effects for a cancelled document.

    - Transfer: revert warehouse to from_warehouse and add Transfer Reversed.
    - Sold / Issue / Consumption: unmark as sold (Reopened).
    - Created / Purchased / Repacked: mark as sold (block barcode).
    """
    if not doc or not getattr(doc, "doctype", None) or not getattr(doc, "name", None):
        return

    # Transfer: revert warehouse using from_warehouse from the transaction row
    transfer_rows = frappe.get_all(
        "Batch Barcode Tracker Transaction",
        filters={
            "reference_document_type": doc.doctype,
            "reference_document_name": doc.name,
            "transaction_type": "Transfer",
        },
        fields=["parent", "from_warehouse", "warehouse"],
    )
    for row in transfer_rows:
        if row.get("from_warehouse"):
            frappe.db.set_value(
                "Batch Barcode Tracker", row["parent"], "warehouse", row["from_warehouse"]
            )
            _append_barcode_transaction(
                row["parent"],
                "Transfer Reversed",
                doc.doctype,
                doc.name,
                warehouse=row["from_warehouse"],
                from_warehouse=row.get("warehouse"),
            )

    # Consumed / sold by this document: unmark as sold
    consumed_types = ("Sold", "Issue", "Consumption")
    consumed_parents = frappe.get_all(
        "Batch Barcode Tracker Transaction",
        filters={
            "reference_document_type": doc.doctype,
            "reference_document_name": doc.name,
            "transaction_type": ["in", consumed_types],
        },
        fields=["parent", "warehouse"],
    )
    for row in consumed_parents:
        unmark_barcode_as_sold(
            row["parent"], doc.doctype, doc.name, warehouse=row.get("warehouse")
        )

    # Created by this document: mark as sold (block)
    created_types = ("Created", "Purchased", "Repacked")
    created_parents = frappe.get_all(
        "Batch Barcode Tracker Transaction",
        filters={
            "reference_document_type": doc.doctype,
            "reference_document_name": doc.name,
            "transaction_type": ["in", created_types],
        },
        fields=["parent", "warehouse"],
    )
    for row in created_parents:
        mark_barcode_as_sold(
            row["parent"],
            doc.doctype,
            doc.name,
            transaction_type="Sold",
            warehouse=row.get("warehouse"),
        )


@frappe.whitelist()
def get_total_qty_from_barcodes():
    barcode_data = frappe.form_dict.get("barcode")
    if not barcode_data:
        return 0  

    try:
        barcode_list = frappe.parse_json(barcode_data)

        barcodes = [entry.get("barcodes") for entry in barcode_list if entry.get("barcodes")]
        
        if not barcodes:
            return 0  

        batch_data = frappe.get_all(
            "Batch Barcode Tracker",
            filters={"barcode": ["in", barcodes]},
            fields=["barcode", "qty"]
        )
        total_qty = sum(flt(entry.get("qty", 0)) for entry in batch_data)
        return total_qty
        
    except Exception as e:
        frappe.log_error(f"Error in get_total_qty_from_barcodes: {str(e)}")
        frappe.throw("Failed to process barcodes. Please check the format and try again.")
        

def update_batch_tracker(doc):
    get_pick_list(doc)

@frappe.whitelist()
def split_purchase_receipt_items():
    """Split items in Purchase Receipt based on custom_split_no"""
    purchase_receipt = frappe.form_dict.get("purchase_receipt")
    pr_doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
    
    items_to_process = [item for item in pr_doc.items]
    
    for item in items_to_process:
        split_no = item.custom_split_no or 1  
        if split_no > 1 and item.qty:
            
            new_items = []
            for i in range(split_no):
                new_item = {
                    'item_code': item.item_code,
                    'qty': item.qty,
                    'uom': item.uom,
                    'stock_uom': item.stock_uom,
                    'conversion_factor': item.conversion_factor,
                    'stock_qty': item.stock_qty,
                    'rate': item.rate,
                    'amount': item.amount,
                    'warehouse': item.warehouse,
                    'batch_no': item.batch_no,
                    'serial_no': item.serial_no,
                    'expense_account': item.expense_account,
                    'cost_center': item.cost_center,
                    'custom_split_no': 1 
                }
                new_items.append(new_item)
            
            pr_doc.remove(item)
            for new_item in new_items:
                pr_doc.append('items', new_item)
    
    pr_doc.save()
    frappe.db.commit()
    
    return pr_doc.name

@frappe.whitelist()
def split_stock_entry_items():
    """Split items in Purchase Receipt based on custom_split_no"""
    stock_entry = frappe.form_dict.get("stock_entry")
    pr_doc = frappe.get_doc("Stock Entry", stock_entry)
    
    items_to_process = [item for item in pr_doc.items]

    for item in items_to_process:
        split_no = item.custom_split_no or 1  
        if split_no > 1 and item.qty:
            new_items = []
            for i in range(split_no):
                new_item = {
                    'item_code': item.item_code,
                    'qty': item.qty,
                    'uom': item.uom,
                    "is_finished_item": item.is_finished_item,
                    'stock_uom': item.stock_uom,
                    'conversion_factor': item.conversion_factor,
                    'rate': item.basic_rate,
                    'basic_amount': item.basic_amount,
                    'amount': item.amount,
                    "s_warehouse": item.s_warehouse,
                    "t_warehouse": item.t_warehouse,
                    'batch_no': item.batch_no,
                    'serial_no': item.serial_no,
                    'expense_account': item.expense_account,
                    'cost_center': item.cost_center,
                    'custom_split_no': 1 
                }
                new_items.append(new_item)
                
            pr_doc.remove(item)
            for new_item in new_items:
                pr_doc.append('items', new_item)
    pr_doc.save()
    frappe.db.commit()
    
    return pr_doc.name


def sanitize_filename(filename):
    """
    Remove special characters and replace spaces with underscores.
    """
    filename = re.sub(r'[^\w\s.-]', '', filename) 
    filename = filename.replace(" ", "_") 
    return filename

@frappe.whitelist()
def generate_image_for_barcode(barcode):
    """
    Generate a barcode image and save it in Frappe's file system.
    """
    try:
        sanitized_filename = sanitize_filename(barcode)
        
        file_path = frappe.get_site_path(f"private/files/{sanitized_filename}.png")

        code = Code128(barcode, writer=ImageWriter())

        code.save(file_path.replace(".png", "")) 

        with open(file_path, "rb") as f:
            file_doc = save_file(f"{sanitized_filename}.png", f.read(), "Batch Barcode Tracker", barcode, is_private=1)
        return file_doc.file_url
    except Exception as e:
        frappe.log_error(f"Error generating barcode image: {str(e)}")
        return None
    
    
@frappe.whitelist()
def get_conversion_factor():
    item_code= frappe.form_dict.get("item_code")
    uom= frappe.form_dict.get("uom")
    """
    Fetches the conversion factor for the given item_code and UOM.
    """
    conversion_factor = frappe.db.get_value(
        "UOM Conversion Detail",
        {"parent": item_code, "uom": uom},
        "conversion_factor"
    )
    conversion_factor = conversion_factor if conversion_factor else 1
    return {"conversion_factor": conversion_factor}
    
    
def get_pick_list(doc):
    pick_list_item = next((item.pick_list_item for item in doc.items if item.pick_list_item), None)
    
    if not pick_list_item:
        return
    
    parent_pick_list = frappe.get_value("Pick List Item", pick_list_item, "parent")
    
    if not parent_pick_list:
        return
    
    pick_list_doc = frappe.get_doc("Pick List", parent_pick_list)
    
    # Mark barcodes as sold with reference to Delivery Note
    for item in pick_list_doc.custom_items:
        if item.barcode:
            mark_barcode_as_sold(item.barcode, doc.doctype, doc.name)
        
    return pick_list_doc

def add_packing_weights_to_delivery_note(doc):
    for item in doc.items:
        pick_list_item = frappe.get_doc("Pick List Item",item.pick_list_item)
        if pick_list_item:
            item.custom_cubic = pick_list_item.custom_cubic
            item.custom_packaging_itemuom = pick_list_item.custom_packaging_itemuom
            item.custom_package_item = pick_list_item.custom_packaging_item
            item.custom_gross_weight = pick_list_item.custom_gross_weight
            item.custom_package_weight = pick_list_item.custom_packing_weight


@frappe.whitelist()
def enqueue_reconcile_all_batch_barcodes(start_date=None, end_date=None):
    """
    Enqueue a background job that reconciles Batch Barcode Trackers against
    submitted Stock Entries (Repack, Manufacture, Material Transfer, Material
    Issue, etc.). Matches by transaction barcode, and also by item + batch +
    full quantity for consume-only rows when the typed barcode does not match.

    Only Stock Entries whose creation date falls within [start_date, end_date]
    are processed (not posting_date, which can be backdated). A consume entry
    is matched only if it was created after the tracker already existed.
    Runs in the background because it may span many trackers and many stock
    entries. Returns the background job id.
    """
    job = frappe.enqueue(
        "inventory_management_extension.inventory_management_extension.utils.reconcile_all_batch_barcodes_job",
        queue="long",
        timeout=7200,
        start_date=start_date,
        end_date=end_date,
    )
    return {"job_id": job.id, "status": "queued", "start_date": start_date, "end_date": end_date}


def _reconcile_date_filters(start_date=None, end_date=None):
    """Filter by Stock Entry creation date, not posting_date."""
    date_filters = ""
    params = []
    if start_date:
        date_filters += " AND DATE(se.creation) >= %s"
        params.append(start_date)
    if end_date:
        date_filters += " AND DATE(se.creation) <= %s"
        params.append(end_date)
    return date_filters, params


def _candidate_barcodes_from_transaction_barcode(date_filters, params):
    rows = frappe.db.sql(
        """
        SELECT sed.custom_transaction_barcode
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE sed.docstatus = 1
            AND sed.custom_transaction_barcode IS NOT NULL
            AND sed.custom_transaction_barcode != ''
            AND (sed.custom_batch_barcode IS NULL OR sed.custom_batch_barcode = '')
        """ + date_filters,
        params,
        as_dict=True,
    )
    typed = {
        row["custom_transaction_barcode"]
        for row in rows
        if row.get("custom_transaction_barcode")
    }
    if not typed:
        return set()
    return set(
        frappe.get_all(
            "Batch Barcode Tracker",
            filters={"barcode": ["in", list(typed)]},
            pluck="barcode",
        )
    )


def _candidate_barcodes_from_item_batch_qty(date_filters, params):
    """
    Unsold trackers that can be paired to a consume-only Stock Entry row by
    item, batch, and full quantity (transaction barcode may be wrong / missing).
    """
    rows = frappe.db.sql(
        """
        SELECT DISTINCT bbt.barcode
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        INNER JOIN `tabBatch Barcode Tracker` bbt
            ON bbt.item_code = sed.item_code
            AND IFNULL(IF(bbt.is_lot = 1, bbt.lot_no, bbt.batch), '') = sed.batch_no
            AND ABS(bbt.qty - sed.qty) < 0.00001
            AND bbt.sold = 0
            AND bbt.docstatus = 1
            AND se.creation >= bbt.creation
            AND (IFNULL(bbt.warehouse, '') = '' OR bbt.warehouse = sed.s_warehouse)
        WHERE sed.docstatus = 1
            AND sed.s_warehouse IS NOT NULL
            AND sed.s_warehouse != ''
            AND (sed.t_warehouse IS NULL OR sed.t_warehouse = '')
            AND (sed.custom_batch_barcode IS NULL OR sed.custom_batch_barcode = '')
        """ + date_filters,
        params,
        as_dict=True,
    )
    return {row["barcode"] for row in rows if row.get("barcode")}


def reconcile_all_batch_barcodes_job(start_date=None, end_date=None):
    """
    Background job: find submitted Stock Entry Detail rows (optionally filtered
    by the parent Stock Entry creation date within [start_date, end_date]) and
    reconcile matching Batch Barcode Trackers. Posting date is ignored because
    it can be backdated to before the tracker existed.

    Candidates come from:
    1. `custom_transaction_barcode` matching an existing tracker while
       `custom_batch_barcode` was left empty/NULL.
    2. Unsold trackers whose item, batch, qty (and warehouse) match a
       consume-only stock entry row — used when the pack is always consumed
       in full but the typed transaction barcode does not match the tracker.

    Reuses BatchBarcodeTracker.reconcile_stock_entries() per tracker, which is
    idempotent (skips Stock Entries already recorded on the tracker). Older
    trackers are processed first so two packs of the same qty claim different rows.
    """
    if not frappe.db.has_column("Stock Entry Detail", "custom_transaction_barcode"):
        frappe.log_error(
            "custom_transaction_barcode column missing on Stock Entry Detail",
            "Reconcile All Batch Barcodes",
        )
        return {"processed_count": 0, "skipped_count": 0}

    date_filters, params = _reconcile_date_filters(start_date, end_date)

    valid_barcodes = _candidate_barcodes_from_transaction_barcode(date_filters, params)
    valid_barcodes |= _candidate_barcodes_from_item_batch_qty(date_filters, params)

    if not valid_barcodes:
        return {"processed_count": 0, "skipped_count": 0}

    ordered = frappe.get_all(
        "Batch Barcode Tracker",
        filters={"name": ["in", list(valid_barcodes)]},
        pluck="name",
        order_by="creation asc",
    )

    results = {"processed": [], "skipped": [], "processed_count": 0, "skipped_count": 0}

    for barcode in ordered:
        try:
            tracker = frappe.get_doc("Batch Barcode Tracker", barcode)
            result = tracker.reconcile_stock_entries(
                start_date=start_date,
                end_date=end_date,
            )
            results["processed"].extend(result.get("processed", []))
            results["skipped"].extend(result.get("skipped", []))
            results["processed_count"] += result.get("processed_count", 0)
            results["skipped_count"] += result.get("skipped_count", 0)
        except Exception as e:
            frappe.log_error(
                f"Reconcile all batch barcodes failed for tracker {barcode}: {e}",
                "Reconcile All Batch Barcodes",
            )
            results["skipped"].append({
                "stock_entry": "N/A",
                "item_code": barcode,
                "reason": f"Tracker error: {e}",
            })
            results["skipped_count"] += 1

    return results
