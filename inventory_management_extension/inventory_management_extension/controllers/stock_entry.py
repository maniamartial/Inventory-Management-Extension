import frappe
from frappe.utils import flt
import random
import barcode
from barcode.writer import ImageWriter
from inventory_management_extension.inventory_management_extension.utils import (
    create_barcode_tracker,
    mark_barcode_as_sold,
    reverse_barcode_transactions_for_doc,
    update_barcode_warehouse_and_add_transfer,
)

def calculate_ean13_check_digit(ean12):
    """
    Calculate the EAN-13 check digit for a 12-digit string.
    """
    odd_sum = sum(int(ean12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(ean12[i]) for i in range(1, 12, 2))
    total = odd_sum + 3 * even_sum
    check_digit = (10 - (total % 10)) % 10
    return check_digit

def generate_ean13():
    """Generate a valid random EAN-13 barcode as a string."""
    ean12 = ''.join(str(random.randint(0, 9)) for _ in range(12))
    check_digit = calculate_ean13_check_digit(ean12)
    return ean12 + str(check_digit)


def before_save(doc, method):
    if doc.stock_entry_type in ["Manufacture", "Material Receipt", "Repack", "Material Transfer", "Material Transfer for Manufacture"]:
        for item in doc.items:
            # Skip if item doesn't need batch
            if not valiadte_item_has_batch(item.item_code):
                continue

            # Manufacture: only generate for finished item
            if doc.stock_entry_type == "Manufacture" and not item.is_finished_item:
                continue
            
            if doc.stock_entry_type == "Material Transfer for Manufacture":
                continue

            # Repack: only generate for items being added (target warehouse exists)
            if doc.stock_entry_type == "Repack" and not item.t_warehouse:
                continue

            # Material Transfer: do not generate new barcodes; we only move existing barcodes
            if doc.stock_entry_type == "Material Transfer":
                continue

            # Material Receipt: all items with batch requirement are valid

            # Generate and set barcode if not already present
            if not item.custom_transaction_barcode:
                item.custom_transaction_barcode = generate_ean13()
                update_barcode_on_item(item.item_code, item.custom_transaction_barcode)

        # After assigning barcodes, generate batches
        generate_batch_no(doc)

                
def update_barcode_on_item(item_code, barcode):
    item_doc = frappe.get_doc("Item", item_code)
    item_doc.append("barcodes", {
        "barcode": barcode
    })
    item_doc.save()
    

def on_submit(doc, method):
    is_lot = False

    # Handle Manufacture: mark source barcodes as sold, create new tracker for finished items
    if doc.stock_entry_type == "Manufacture":
        handle_manufacture(doc)
    
    # Handle Material Receipt (existing logic - only create new trackers)
    elif doc.stock_entry_type == "Material Receipt":
        for item in doc.items:
            if item.custom_transaction_barcode:
                create_barcode_tracker(
                    item.item_code,
                    item.custom_transaction_barcode,
                    item.batch_no,
                    item.qty,
                    item.t_warehouse,
                    item.custom_barcode_image,
                    reference_document_type=doc.doctype,
                    reference_document_name=doc.name
                )
                update_serial_and_batch(doc, item)
        # Tick Batch Barcode Reconciliation new_barcodes where this barcode was created
        _tick_new_barcodes_tracker_created(doc)
    
    # Handle Repack: mark source barcodes as sold, create new tracker for target
    elif doc.stock_entry_type == "Repack":
        handle_repack(doc)
    
    # Handle Material Transfer: mark source barcodes as sold, create new tracker for target
    elif doc.stock_entry_type == "Material Transfer":
        handle_material_transfer(doc)
        
    elif doc.stock_entry_type == "Material Transfer for Manufacture":
        handle_material_transfer(doc)
    
    # Handle Material Issue: mark selected barcodes as sold, no new tracker
    elif doc.stock_entry_type == "Material Issue":
        handle_material_issue(doc)
        _tick_missing_barcodes_issued(doc)
    
    # Handle other stock entry types based on source/target warehouse
    else:
        handle_other_stock_entry_types(doc)


def on_cancel(doc, method):
    """
    Reverse barcode effects when a Stock Entry is cancelled.
    This uses generic logic based on the reference fields on Batch Barcode Tracker.
    """
    reverse_barcode_transactions_for_doc(doc)


def resolve_batch_barcode(item):
    """
    Resolve the Batch Barcode Tracker for a Stock Entry item.

    Prefers item.custom_batch_barcode. When the user did not select a batch
    barcode, falls back to resolving the tracker by item.custom_transaction_barcode.
    Batch Barcode Tracker is autonamed by the barcode field, so the tracker
    name equals the transaction barcode value when a tracker exists for it.
    """
    if item.custom_batch_barcode:
        return item.custom_batch_barcode

    if item.custom_transaction_barcode:
        if frappe.db.exists("Batch Barcode Tracker", item.custom_transaction_barcode):
            return item.custom_transaction_barcode

    return None


def handle_manufacture(doc):
    """
    Handle Manufacture:
    - If existing barcode moves s_warehouse -> t_warehouse: Transfer only (update warehouse, record Transfer; do NOT mark sold).
    - If existing barcode leaves s_warehouse only (no target): Consumption (mark as sold).
    - Finished items: create new tracker (transaction_type=Created).
    """
    is_lot = False
    if doc.custom_create_lot == 1:
        is_lot = True

    for item in doc.items:
        batch_barcode = resolve_batch_barcode(item)

        # Existing barcode: transfer (s -> t) = only update warehouse + Transfer; no sold
        if batch_barcode and item.s_warehouse and item.t_warehouse:
            update_barcode_warehouse_and_add_transfer(
                batch_barcode,
                item.t_warehouse,
                item.s_warehouse,
                doc.doctype,
                doc.name,
            )
        # Existing barcode: consumption (s only, no t)
        elif batch_barcode and item.s_warehouse:
            mark_barcode_as_sold(
                batch_barcode,
                doc.doctype,
                doc.name,
                transaction_type="Consumption",
                warehouse=item.s_warehouse,
            )

        # Finished items: create tracker with Created
        if item.is_finished_item and item.t_warehouse and item.custom_transaction_barcode and item.batch_no:
            create_barcode_tracker(
                item.item_code,
                item.custom_transaction_barcode,
                item.batch_no,
                item.qty,
                item.t_warehouse,
                item.custom_barcode_image,
                is_lot=is_lot,
                reference_document_type=doc.doctype,
                reference_document_name=doc.name,
                transaction_type="Created",
            )
            update_serial_and_batch(doc, item)


def handle_repack(doc):
    """
    Handle Repack:
    - If existing barcode moves s_warehouse -> t_warehouse: Transfer only (no sold).
    - If existing barcode s_warehouse only: Consumption.
    - Target items: create new tracker (Repacked).
    """
    is_lot = False
    if doc.custom_create_lot == 1:
        is_lot = True

    for item in doc.items:
        batch_barcode = resolve_batch_barcode(item)

        if batch_barcode and item.s_warehouse and item.t_warehouse:
            update_barcode_warehouse_and_add_transfer(
                batch_barcode,
                item.t_warehouse,
                item.s_warehouse,
                doc.doctype,
                doc.name,
            )
        elif batch_barcode and item.s_warehouse:
            mark_barcode_as_sold(
                batch_barcode,
                doc.doctype,
                doc.name,
                transaction_type="Consumption",
                warehouse=item.s_warehouse,
            )

        if item.t_warehouse and item.custom_transaction_barcode and item.batch_no:
            create_barcode_tracker(
                item.item_code,
                item.custom_transaction_barcode,
                item.batch_no,
                item.qty,
                item.t_warehouse,
                item.custom_barcode_image,
                is_lot=is_lot,
                reference_document_type=doc.doctype,
                reference_document_name=doc.name,
                transaction_type="Repacked",
            )
            update_serial_and_batch(doc, item)


def handle_material_transfer(doc):
    """
    Handle Material Transfer:
    - Do NOT create new barcode or mark as sold. Only update warehouse on
      existing Batch Barcode Tracker and record a Transfer transaction.
    """
    for item in doc.items:
        batch_barcode = resolve_batch_barcode(item)

        if batch_barcode and item.s_warehouse and item.t_warehouse:
            update_barcode_warehouse_and_add_transfer(
                batch_barcode,
                item.t_warehouse,
                item.s_warehouse,
                doc.doctype,
                doc.name,
            )


def handle_material_issue(doc):
    """
    Handle Material Issue: mark selected batch barcodes as sold with Issue.
    """
    for item in doc.items:
        batch_barcode = resolve_batch_barcode(item)

        if batch_barcode:
            mark_barcode_as_sold(
                batch_barcode,
                doc.doctype,
                doc.name,
                transaction_type="Issue",
                warehouse=item.s_warehouse,
            )


def handle_other_stock_entry_types(doc):
    """
    Other stock entry types: stock out = Issue, stock in = Created,
    both = Consumption + Created (or Repacked for target if applicable).
    """
    for item in doc.items:
        has_source = bool(item.s_warehouse)
        has_target = bool(item.t_warehouse)

        batch_barcode = resolve_batch_barcode(item)

        if has_source and not has_target:
            if batch_barcode:
                mark_barcode_as_sold(
                    batch_barcode,
                    doc.doctype,
                    doc.name,
                    transaction_type="Issue",
                    warehouse=item.s_warehouse,
                )

        elif has_target and not has_source:
            if item.custom_transaction_barcode and item.batch_no:
                create_barcode_tracker(
                    item.item_code,
                    item.custom_transaction_barcode,
                    item.batch_no,
                    item.qty,
                    item.t_warehouse,
                    item.custom_barcode_image,
                    reference_document_type=doc.doctype,
                    reference_document_name=doc.name,
                    transaction_type="Created",
                )
                update_serial_and_batch(doc, item)

        elif has_source and has_target:
            # Same barcode moving s -> t = Transfer only (update warehouse, no sold)
            if batch_barcode:
                update_barcode_warehouse_and_add_transfer(
                    batch_barcode,
                    item.t_warehouse,
                    item.s_warehouse,
                    doc.doctype,
                    doc.name,
                )
            if item.custom_transaction_barcode and item.batch_no:
                create_barcode_tracker(
                    item.item_code,
                    item.custom_transaction_barcode,
                    item.batch_no,
                    item.qty,
                    item.t_warehouse,
                    item.custom_barcode_image,
                    reference_document_type=doc.doctype,
                    reference_document_name=doc.name,
                    transaction_type="Created",
                )
                update_serial_and_batch(doc, item)
                
                
def update_serial_and_batch(doc, item):
    entry = frappe.get_value(
        "Serial and Batch Bundle",
        {"voucher_no": doc.name, "voucher_type": doc.doctype, "item_code": item.item_code},
        "name"
    )
    if entry:
        bundle_doc = frappe.get_doc("Serial and Batch Bundle", entry)

        # Update the custom_barcode field in the entries child table
        for row in bundle_doc.entries:
            row.custom_barcode = item.custom_transaction_barcode

        bundle_doc.save(ignore_permissions=True)


def _tick_new_barcodes_tracker_created(ste_doc):
	"""After Material Receipt submit: tick new_barcodes row and add Items row (same as scan) for each barcode created."""
	barcodes_created = [item.custom_transaction_barcode for item in (ste_doc.items or []) if item.custom_transaction_barcode]
	if not barcodes_created:
		return
	# Batch Barcode Tracker name usually equals transactional barcode (autoname field:barcode)
	for barcode in set(barcodes_created):
		reconciliations = frappe.db.sql(
			"""SELECT DISTINCT parent FROM `tabAdditional Batch Barcode`
			   WHERE parenttype = 'Batch Barcode Reconciliation' AND barcode = %s""",
			(barcode,),
			as_dict=True,
		)
		for r in reconciliations:
			doc = frappe.get_doc("Batch Barcode Reconciliation", r.parent)
			existing_bc = {item.batch_barcode for item in (doc.items or []) if item.batch_barcode}
			for row in (doc.new_barcodes or []):
				if row.barcode == barcode:
					row.batch_barcode_tracker_created = 1
			# Append item line like barcode scan (tracker name as batch_barcode link)
			tracker_name = barcode
			if frappe.db.exists("Batch Barcode Tracker", tracker_name):
				tracker = frappe.db.get_value(
					"Batch Barcode Tracker",
					tracker_name,
					["name", "barcode", "item_code", "batch", "warehouse", "qty", "uom"],
					as_dict=True,
				)
				if tracker and tracker.name not in existing_bc:
					# Match SE line for qty/warehouse from this submission
					se_item = next(
						(i for i in (ste_doc.items or []) if i.custom_transaction_barcode == barcode),
						None,
					)
					qty = flt(se_item.qty) if se_item else flt(tracker.get("qty"))
					wh = (se_item.t_warehouse if se_item and se_item.t_warehouse else None) or tracker.get("warehouse")
					doc.append(
						"items",
						{
							"barcode": tracker.get("barcode") or barcode,
							"item_code": tracker.item_code,
							"warehouse": wh,
							"batch_no": tracker.batch,
							"batch_barcode": tracker.name,
							"qty": qty,
							"stock_uom": tracker.get("uom"),
							"use_serial_batch_fields": 1,
						},
					)
			doc.flags.ignore_validate_update_after_submit = True
			doc.save(ignore_permissions=True)


def _parse_barcode_link_list(barcode_list_json):
	"""Parse custom_missing_barcode_list (JSON array or newline/comma-separated)."""
	if not barcode_list_json:
		return []
	if isinstance(barcode_list_json, (list, tuple, set)):
		return list(barcode_list_json)
	s = str(barcode_list_json).strip()
	if not s:
		return []
	try:
		parsed = frappe.parse_json(s)
		if isinstance(parsed, list):
			return [str(x) for x in parsed]
	except Exception:
		pass
	# Fallback: comma or newline separated
	parts = []
	for part in s.replace("\n", ",").split(","):
		p = part.strip()
		if p:
			parts.append(p)
	return parts


def _tick_missing_barcodes_issued(ste_doc):
	"""After Material Issue submit: tick batch_barcode_tracker_update on reconciliation (from Stock Entry custom fields)."""
	recon_name = ste_doc.get("custom_batch_barcode_reconciliation") if hasattr(
		ste_doc, "get"
	) else None
	if not recon_name:
		recon_name = frappe.db.get_value(
			"Stock Entry", ste_doc.name, "custom_batch_barcode_reconciliation"
		)
	barcode_list_json = ste_doc.get("custom_missing_barcode_list") if hasattr(
		ste_doc, "get"
	) else None
	if not barcode_list_json:
		barcode_list_json = frappe.db.get_value(
			"Stock Entry", ste_doc.name, "custom_missing_barcode_list"
		)
	if not recon_name or not barcode_list_json:
		return
	barcode_list = _parse_barcode_link_list(barcode_list_json)
	barcode_set = set(barcode_list)
	if not barcode_set:
		return
	try:
		doc = frappe.get_doc("Batch Barcode Reconciliation", recon_name)
	except frappe.DoesNotExistError:
		frappe.log_error(
			f"Batch Barcode Reconciliation {recon_name} not found for Stock Entry {ste_doc.name}",
			"Tick Missing Barcodes",
		)
		return
	for row in (doc.missing_batch_barcodes or []):
		if not row.barcode:
			continue
		# Link field may be compared as string name
		if str(row.barcode) in barcode_set or row.barcode in barcode_set:
			row.batch_barcode_tracker_update = 1
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)


def latest_batch(batch_prefix):
    latest_batch = frappe.db.sql(
        """SELECT batch_id FROM `tabBatch`
        WHERE batch_id LIKE %s
        ORDER BY creation DESC LIMIT 1""",
        (batch_prefix + "%",), as_dict=True
    )

    if latest_batch:
        last_number = int(latest_batch[0].batch_id.split("-")[-1])
        new_number = f"{last_number + 1:05}"
    else:
        new_number = "0001"

    new_batch_no = f"{batch_prefix}{new_number}"
    return new_batch_no

def create_batch(batch_no, item_code):
    batch = frappe.new_doc("Batch")
    batch.batch_id = batch_no
    batch.item = item_code
    batch.insert()
    return batch


def generate_year_prefixed_batch():
    """
    Generate batch number with year prefix in format [YY]-Series
    Example: 24-00001, 24-00002, 25-00001
    """
    from datetime import datetime
    
    # Get current year as 2-digit string
    current_year = datetime.now().strftime("%y")
    year_prefix = f"{current_year}-"
    
    # Find the latest batch for current year
    latest_batch = frappe.db.sql(
        """SELECT batch_id FROM `tabBatch`
        WHERE batch_id LIKE %s
        ORDER BY creation DESC LIMIT 1""",
        (year_prefix + "%",), as_dict=True
    )
    
    if latest_batch:
        # Extract the series number from the latest batch
        try:
            series_part = latest_batch[0].batch_id.split("-")[-1]
            next_series = int(series_part) + 1
        except (ValueError, IndexError):
            # If parsing fails, start from 1
            next_series = 1
    else:
        # No batch exists for current year, start from 1
        next_series = 1
    
    # Format series as 5-digit number with leading zeros
    series_formatted = f"{next_series:05d}"
    
    # Combine year prefix with series
    new_batch_id = f"{year_prefix}{series_formatted}"
    
    return new_batch_id

def generate_code128():
    """
    Generate a valid random Code 128 barcode as a string and save it as an image.
    """
    random_number = ''.join(str(random.randint(0, 9)) for _ in range(12))
    
    code128 = barcode.get_barcode_class('code128')
    
    barcode_instance = code128(random_number, writer=ImageWriter())
    
    filename = barcode_instance.save('code128_barcode')
    
    return random_number, filename

def generate_batch_no(doc):
    item_batch_map = {}
    
    for item in doc.items:
        if frappe.get_doc("Item", item.item_code).has_batch_no == 1:
            if item.batch_no: 
                continue
            item.use_serial_batch_fields = 1
            if doc.doctype=="Stock Entry" and doc.stock_entry_type == "Manufacture" and not item.is_finished_item:
                continue
            
            if item.item_code in item_batch_map:
                item.batch_no = item_batch_map[item.item_code]
                continue
            
            # Generate batch with year prefix [YY]-Series format
            new_batch_id = generate_year_prefixed_batch()
        
            batch = frappe.get_doc({
                "doctype": "Batch",
                "batch_id": new_batch_id,
                "item": item.item_code,
                "expiry_date": item.get("expiry_date")
            })
            batch.insert(ignore_permissions=True)
        
            item.batch_no = new_batch_id
            item_batch_map[item.item_code] = new_batch_id
            
            
def valiadte_item_has_batch(item_code):
    item_doc = frappe.get_doc("Item", item_code)
    if item_doc.has_batch_no == 1:
        return True
    return False