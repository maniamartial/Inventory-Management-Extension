frappe.ui.form.on('Pick List', {
    refresh: function(frm) {
        set_custom_items_queries(frm);
        
        // Refresh the list of used barcodes in submitted pick lists
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.controllers.pick_list.get_used_barcodes_in_submitted_picklists",
            callback: function(r) {
                if (!r.exc && r.message) {
                    frm._used_barcodes_in_submitted_picklists = r.message || [];
                } else {
                    frm._used_barcodes_in_submitted_picklists = [];
                }
            }
        });

         if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Sales Invoice'), function() {
                frappe.call({
                    method: "inventory_management_extension.inventory_management_extension.controllers.pick_list.picklist_to_invoice",
                    args: {
                        picklist_name: frm.doc.name
                    },
                    callback: function(r) {
                        if (!r.exc && r.message) {
                            frappe.set_route("Form", "Sales Invoice", r.message);
                        }
                    }
                });
            }, __("Create"));
        }

        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Fetch Items From Order'), function() {
                imx_fetch_items_from_order(frm);
            });
        }

    },
    onload: function(frm, cdt, cdn) {
        // Fetch barcodes already used in submitted Pick Lists
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.controllers.pick_list.get_used_barcodes_in_submitted_picklists",
            callback: function(r) {
                if (!r.exc && r.message) {
                    frm._used_barcodes_in_submitted_picklists = r.message || [];
                } else {
                    frm._used_barcodes_in_submitted_picklists = [];
                }
            }
        });

        set_custom_items_queries(frm);
        frm.refresh_field("custom_items");
        frm.refresh();

    }
,    

  
        before_save: function(frm) {
            // Validate duplicate barcodes in custom_items table
            let custom_items = frm.doc.custom_items || [];
            let barcode_map = {};
            let duplicate_barcodes = [];
            
            custom_items.forEach((row) => {
                if (row.barcode) {
                    if (barcode_map[row.barcode]) {
                        // Barcode already exists
                        if (!duplicate_barcodes.includes(row.barcode)) {
                            duplicate_barcodes.push(row.barcode);
                        }
                    } else {
                        barcode_map[row.barcode] = true;
                    }
                }
            });
            
            if (duplicate_barcodes.length > 0) {
                frappe.msgprint({
                    title: __('Duplicate Barcodes Found'),
                    message: __('The following barcodes have been repeated in the custom_items table:<br><br><b>' + duplicate_barcodes.join(', ') + '</b><br><br>Please remove the duplicate barcodes before proceeding.'),
                    indicator: 'orange'
                });
                frappe.validated = false;
                return false;
            }
            
            // if(frm.is_new()){
            //     getSalesOrder(frm);

            // }
            // The standard Item Locations table must mirror the scanned Items
            // table: rebuild it for a new document, when "Update Items" is
            // ticked, whenever the scanned rows changed, and while the standard
            // table is still empty.
            let pick_list_extension = frm.doc.custom_items || [];
            if (!pick_list_extension.length) {
                // Nothing scanned: leave the standard Item Locations table
                // (e.g. a pick list created from a Sales Order) untouched.
                return;
            }
            let current_state = JSON.stringify(pick_list_extension);
            let previous_state = frm.__last_custom_items_state
                ? JSON.stringify(frm.__last_custom_items_state)
                : null;
            let force_update = frm.is_new() || cint(frm.doc.custom_update_items) === 1;
            let locations_missing = !(frm.doc.locations || []).length;

            if (!force_update && !locations_missing && previous_state === current_state) {
                console.log("No changes detected in custom_items. Skipping update.");
                return;
            }

            frm.__last_custom_items_state = JSON.parse(current_state);
    
            let grouped_items = {};
            let barcode_counts = {};

            // Keep the Sales Order linkage already present on the location rows
            // (e.g. a pick list created with "Get Items From > Sales Order").
            const existing_location_map = {};
            (frm.doc.locations || []).forEach(loc => {
                existing_location_map[loc.item_code + "-" + (loc.batch_no || "NoBatch")] = loc;
            });

            pick_list_extension.forEach(row => {
                let key = row.item_code + "-" + (row.batch_no || "NoBatch");
                
                // Initialize the barcode count for this key if not exists
                if (!barcode_counts[key]) {
                    barcode_counts[key] = 0;
                }
                
                // Each row in the pick_list_extension represents one barcode
                barcode_counts[key]++;
            });

            pick_list_extension.forEach(row => {
                let key = row.item_code + "-" + (row.batch_no || "NoBatch");
                if (!grouped_items[key]) {
                    const previous = existing_location_map[key] || {};
                    grouped_items[key] = {
                        item_code: row.item_code,
                        batch_no: row.batch_no || "NoBatch",
                        warehouse: row.warehouse || previous.warehouse,
                        // qty is expressed in `uom`; stock_qty / picked_qty are
                        // always kept in the Stock UOM.
                        uom: row.uom || previous.uom,
                        stock_uom: row.stock_uom || previous.stock_uom,
                        conversion_factor: flt(row.conversion_factor) || flt(previous.conversion_factor) || 1,
                        sales_order: row.sales_order || previous.sales_order,
                        sales_order_item: row.sales_order_item || previous.sales_order_item,
                        // Packaging details come from the scanned row and are
                        // copied onto the standard Item Locations row.
                        packaging_item: row.packaging_item,
                        package_weight: flt(row.package_weight),
                        packaging_itemuom: row.packaging_itemuom,
                        cubic: flt(row.cubic),
                        stock_qty: 0,
                        barcode_count: barcode_counts[key]
                    };
                }
                // Accumulate in Stock UOM so rows entered in the stock UOM and
                // rows entered in the transaction UOM stay comparable.
                const row_cf = flt(row.conversion_factor) || 1;
                grouped_items[key].stock_qty += flt(row.stock_qty) || (flt(row.qty) * row_cf);
           
            });
    
            frm.clear_table("locations");
            Object.values(grouped_items).forEach(data => {
                const cf = flt(data.conversion_factor) || 1;
                const stock_qty = flt(data.stock_qty);
                const barcode_count = flt(data.barcode_count);
                let new_row = frm.add_child("locations");
                new_row.item_code = data.item_code;
                new_row.use_serial_batch_fields = 1;
                new_row.batch_no = data.batch_no === "NoBatch" ? "" : data.batch_no;
                new_row.warehouse = data.warehouse;
                new_row.uom = data.uom || data.stock_uom;
                new_row.stock_uom = data.stock_uom || data.uom;
                new_row.conversion_factor = cf;
                // qty in `uom` (the Sales Order UOM when the pick list is linked)
                new_row.qty = stock_qty / cf;
                new_row.stock_qty = stock_qty;
                new_row.picked_qty = stock_qty;
                new_row.custom_barcode_no = data.barcode_count;
                // Packaging details (weight is physical -> use the Stock UOM qty)
                new_row.custom_packaging_item = data.packaging_item;
                new_row.custom_packing_weight = flt(data.package_weight);
                new_row.custom_packaging_itemuom = data.packaging_itemuom;
                new_row.custom_cubic = flt(data.cubic) * barcode_count;
                new_row.custom_gross_weight =
                    (flt(data.package_weight) * barcode_count) + stock_qty;
                if (data.sales_order) {
                    new_row.sales_order = data.sales_order;
                }
                if (data.sales_order_item) {
                    new_row.sales_order_item = data.sales_order_item;
                }
            });
            frm.doc.custom_update_items = 0;
            frm.refresh_field("locations"); 
        },
      
        custom_scan_transactional_barcode: function(frm) {
                const barcode = frm.doc.custom_scan_transactional_barcode;
                if (!barcode) return;
        
                // Check if barcode is already used in submitted pick lists
                const used_barcodes = frm._used_barcodes_in_submitted_picklists || [];
                if (used_barcodes.includes(barcode)) {
                    frappe.msgprint({
                        title: __('Barcode Already Used'),
                        message: __('This barcode has already been used in a submitted Pick List and cannot be used again.'),
                        indicator: 'orange'
                    });
                    frm.set_value('custom_scan_transactional_barcode', '');
                    return;
                }
        
                frappe.call({
                    method: 'inventory_management_extension.inventory_management_extension.utils.get_batch_barcode_pack_details',
                    args: {
                        barcode: barcode,
                        // Use the Sales Order Item (child table) UOM as the
                        // transactional UOM when the pick list is linked to an SO.
                        sales_order: frm.doc.custom_sales_order || undefined
                    },
                    callback: function(r) {
                        if (r.message) {
                            const data = r.message;
                            
                            // Additional check: verify barcode is not sold
                            if (data.sold) {
                                frappe.msgprint({
                                    title: __('Barcode Already Sold'),
                                    message: __('This barcode has already been marked as sold and cannot be used.'),
                                    indicator: 'orange'
                                });
                                frm.set_value('custom_scan_transactional_barcode', '');
                                return;
                            }
        
                            const row = frm.add_child('custom_items');
                            row.item_code = data.item_code;
                            row.batch_no = data.batch;
                            row.barcode = data.name;
                            // Default to the Sales Order Item (child table) UOM when
                            // the pick list is linked to a Sales Order; otherwise use
                            // the pack transaction UOM, falling back to Stock UOM.
                            // qty is expressed in `uom`, stock_qty in Stock UOM.
                            row.uom = data.selected_uom || data.transaction_uom || data.stock_uom || data.uom || 'Nos';
                            row.stock_uom = data.stock_uom || data.uom || row.uom;
                            row.conversion_factor = data.selected_conversion_factor || 1;
                            row.qty = data.selected_qty !== undefined && data.selected_qty !== null
                                ? data.selected_qty
                                : (data.stock_qty || data.qty);
                            row.stock_qty = data.selected_stock_qty !== undefined && data.selected_stock_qty !== null
                                ? data.selected_stock_qty
                                : (data.stock_qty || data.qty);
                            row.warehouse = data.warehouse;
                            if (data.sales_order) {
                                row.sales_order = data.sales_order;
                            }
                            if (data.sales_order_item) {
                                row.sales_order_item = data.sales_order_item;
                            }
        
                            frm.refresh_field('custom_items');
                            frm.set_value('custom_scan_transactional_barcode', ''); 
                        } else {
                            frappe.msgprint(`No record found for barcode: ${barcode}`);
                        }
                    }
                });
            }
       

});

frappe.ui.form.on('Pick List Extension', {
    barcode: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.barcode) {
            return;
        }
        // Honor the UOM already chosen on the row. When none is chosen the
        // server defaults to the Sales Order Item (child table) UOM, then to the
        // pack transaction UOM, then to the Stock UOM.
        imx_fetch_pack_details(frm, row, row.uom, function (pack) {
            if (!pack) {
                frappe.msgprint(__('No such barcode found'));
                frappe.model.set_value(cdt, cdn, 'barcode', '');
                return;
            }
            if (pack.sold) {
                frappe.msgprint(__('This barcode is already sold/consumed.'));
                frappe.model.set_value(cdt, cdn, 'barcode', '');
                return;
            }
            imx_apply_pack_to_row(frm, cdt, cdn, pack);
        });
    },
    // Switching the UOM re-fills the qty for that UOM and always keeps the
    // picked qty in the Stock UOM in sync.
    uom: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.__imx_applying_pack || !row.barcode) {
            return;
        }
        imx_fetch_pack_details(frm, row, row.uom, function (pack) {
            if (pack && !pack.sold) {
                imx_apply_pack_to_row(frm, cdt, cdn, pack);
            }
        });
    },
    package_weight: function(frm, cdt, cdn) {
        update_gross_weight(frm, cdt, cdn);
    },
});

frappe.ui.form.on('Pick List Item', {
    custom_packaging_item: function(frm, cdt, cdn) {
        // update_gross_weight_items(frm, cdt, cdn);
    }
});

function update_gross_weight(frm, cdt, cdn) {
    let child_table = frm.doc.custom_items || [];
    
    child_table.forEach(row => {
        if (!row.packaging_item) return;

        // Weight is physical: use the qty in the Stock UOM even when the row
        // qty is expressed in the transaction (Sales Order) UOM.
        const picked_qty = flt(row.stock_qty) || flt(row.qty);
        const package_weight = flt(row.package_weight);

        if (row.packaging_itemuom === row.stock_uom) {
            let gross_weight = picked_qty + package_weight;
            frappe.model.set_value(row.doctype, row.name, 'gross_weight', gross_weight);
        } else {
            frappe.call({
                method: "inventory_management_extension.inventory_management_extension.utils.get_conversion_factor",
                args: {
                    item_code: row.packaging_item,
                    uom: row.packaging_itemuom
                },
                callback: function(r) {
                    if (r.message && r.message.conversion_factor) {
                        let conversion_factor = r.message.conversion_factor;
                        let converted_qty = picked_qty * conversion_factor; // Convert quantity
                        let gross_weight = converted_qty + package_weight;
                        frappe.model.set_value(row.doctype, row.name, 'gross_weight', gross_weight);
                    } else {
                        frappe.msgprint(`Conversion factor not found for ${row.packaging_itemuom}`);
                    }
                }
            });
        }
    });
}

function update_gross_weight_items(frm, cdt, cdn) {
    let child_table = frm.doc.locations || [];
   
    child_table.forEach(row => {
        if (!row.custom_packaging_item)
            return;
        
        if (row.custom_packaging_itemuom === row.stock_uom) {
           
            let gross_weight = row.qty + row.custom_packing_weight;
            frappe.model.set_value(cdt, cdn, 'custom_gross_weight', gross_weight);
        } else {
        
            frappe.call({
                method: "inventory_management_extension.inventory_management_extension.utils.get_conversion_factor",
                args: {
                    item_code: row.custom_packaging_item,
                    uom: row.custom_packaging_itemuom
                },
                callback: function(r) {
                    // alert(row.custom_packaging_item);
                    if (r.message && r.message.conversion_factor) {
                        let conversion_factor = r.message.conversion_factor;
                        let converted_qty = row.stock_qty * conversion_factor; // Convert quantity
                        let gross_weight = converted_qty + row.custom_packing_weight;
                        frappe.model.set_value(cdt, cdn, 'custom_gross_weight', gross_weight);
                        frappe.model.set_value(cdt, cdn, 'custom_packaging_item', row.custom_packaging_item);
                    } else {
                        frappe.msgprint(`Conversion factor not found for ${row.packaging_itemuom}`);
                    }
                }
            });
        }
    });
}

function getSalesOrder(frm){
    let sales_order = '';
        for (let i = 0; i < frm.doc.custom_items.length; i++) {
            let item = frm.doc.custom_items[i];
            if (item.sales_order) {
                sales_order= item.sales_order;
            }
        }
        frm.doc.custom_sales_order =sales_order;
        frm.refresh_field("custom_sales_order");
}

// ---------------------------------------------------------------------------
// UOM helpers
//
// A Batch Barcode Tracker carries both a Transaction UOM and a Stock UOM.
// A Pick List row must:
//   * fill `qty` with the quantity that matches the UOM chosen on the row
//     (`transaction_qty` for the transaction UOM, `stock_qty` for the Stock UOM)
//   * always fill `stock_qty` (picked qty) in the Stock UOM
//   * default to the Sales Order Item (child table) UOM as the transactional
//     UOM when the Pick List is linked to a Sales Order.
// ---------------------------------------------------------------------------

const IMX_PACK_DETAILS_METHOD =
    'inventory_management_extension.inventory_management_extension.utils.get_batch_barcode_pack_details';

function imx_get_sales_order(frm, row) {
    return frm.doc.custom_sales_order || (row && row.sales_order) || undefined;
}

function imx_fetch_pack_details(frm, row, chosen_uom, callback) {
    frappe.call({
        method: IMX_PACK_DETAILS_METHOD,
        args: {
            barcode: row.barcode,
            sales_order: imx_get_sales_order(frm, row),
            uom: chosen_uom || undefined,
        },
        callback: function (r) {
            callback(r && r.message ? r.message : null);
        },
    });
}

// Apply server-resolved pack qty/UOM values onto a Pick List Extension row.
function imx_apply_pack_to_row(frm, cdt, cdn, pack) {
    const row = locals[cdt][cdn];
    // Guard so the `uom` handler does not refetch in a loop.
    row.__imx_applying_pack = true;

    const tasks = [];
    // The scanned barcode defines the item on the row (which also scopes the
    // Batch dropdown to that item).
    imx_set_row_item_code(frm, cdt, cdn, pack, tasks);
    tasks.push(
        frappe.model.set_value(cdt, cdn, 'uom', pack.selected_uom || pack.uom),
        frappe.model.set_value(cdt, cdn, 'conversion_factor', flt(pack.selected_conversion_factor) || 1),
        frappe.model.set_value(cdt, cdn, 'qty', flt(pack.selected_qty)),
        frappe.model.set_value(cdt, cdn, 'stock_qty', flt(pack.selected_stock_qty)),
        frappe.model.set_value(cdt, cdn, 'stock_uom', pack.stock_uom),
    );

    if (pack.sales_order_item) {
        tasks.push(frappe.model.set_value(cdt, cdn, 'sales_order', pack.sales_order));
        tasks.push(frappe.model.set_value(cdt, cdn, 'sales_order_item', pack.sales_order_item));
    }
    if (pack.batch) {
        tasks.push(frappe.model.set_value(cdt, cdn, 'batch_no', pack.batch));
    }
    if (pack.warehouse) {
        tasks.push(frappe.model.set_value(cdt, cdn, 'warehouse', pack.warehouse));
    }

    Promise.all(tasks).then(imx_done, imx_done);

    function imx_done() {
        row.__imx_applying_pack = false;
        frm.refresh_field('custom_items');
    }
}


// ---------------------------------------------------------------------------
// Link field queries for the custom Items table (`custom_items`)
//
// The Batch column must only offer batches that belong to the item chosen on
// that same row. The Barcode column keeps excluding barcodes already used on
// other rows / in submitted pick lists.
// ---------------------------------------------------------------------------

function set_custom_items_queries(frm) {
    frm.set_query('batch_no', 'custom_items', function (doc, cdt, cdn) {
        const row = locals[cdt][cdn] || {};
        if (!row.item_code) {
            // No item on the row yet -> offer nothing instead of every batch.
            return { filters: { item: '__no_item_selected__' } };
        }
        return {
            query: 'erpnext.controllers.queries.get_batch_no',
            filters: {
                item_code: row.item_code,
                // Only used by ERPNext once the warehouse is known on the row.
                warehouse: row.warehouse || undefined
            }
        };
    });

    frm.set_query('barcode', 'custom_items', function (doc, cdt, cdn) {
        const row = locals[cdt][cdn] || {};
        const selected_barcodes = (frm.doc.custom_items || [])
            .filter(r => r.name !== cdn && r.barcode)
            .map(r => r.barcode);

        // Combine selected barcodes with barcodes used in submitted pick lists
        const used_barcodes_in_submitted = frm._used_barcodes_in_submitted_picklists || [];
        const all_excluded_barcodes = [...new Set([...selected_barcodes, ...used_barcodes_in_submitted])];

        return {
            query: 'inventory_management_extension.inventory_management_extension.controllers.pick_list.get_barcode_query',
            filters: {
                item_code: row.item_code,
                batch: row.batch_no || undefined,
                sold: 0,
                exclude_barcodes: all_excluded_barcodes
            }
        };
    });
}

// The scanned barcode defines the item on the row, which also scopes the Batch
// dropdown to that item.
function imx_set_row_item_code(frm, cdt, cdn, pack, tasks) {
    const row = locals[cdt][cdn];
    if (pack.item_code && pack.item_code !== row.item_code) {
        tasks.push(frappe.model.set_value(cdt, cdn, 'item_code', pack.item_code));
    }
}


// ---------------------------------------------------------------------------
// "Fetch Items From Order"
//
// Shows the items of the Pick List's Sales Order, asks how many splits each
// item has (and an optional transaction id), then adds one row per split to the
// custom Items table so the batch barcode can be chosen against each split.
// ---------------------------------------------------------------------------

function imx_fetch_items_from_order(frm) {
    if (!frm.doc.custom_sales_order) {
        frappe.msgprint(__('Link a Sales Order on this Pick List first.'));
        return;
    }

    frappe.call({
        method: 'inventory_management_extension.inventory_management_extension.controllers.pick_list.get_sales_order_items_for_pick_list',
        args: { sales_order: frm.doc.custom_sales_order },
        freeze: true,
        freeze_message: __('Fetching items from {0}...', [frm.doc.custom_sales_order]),
        callback: function (r) {
            const items = r.message || [];
            if (!items.length) {
                frappe.msgprint(__('No items found on {0}.', [frm.doc.custom_sales_order]));
                return;
            }
            imx_show_fetch_items_dialog(frm, items);
        },
    });
}

function imx_show_fetch_items_dialog(frm, items) {
    const dialog = new frappe.ui.Dialog({
        title: __('Fetch Items From Order : {0}', [frm.doc.custom_sales_order]),
        size: 'extra-large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'items_area',
            },
        ],
        primary_action_label: __('Add'),
        primary_action: function () {
            if (imx_add_fetched_items(frm, dialog, items)) {
                dialog.hide();
            }
        },
    });

    const $area = dialog.fields_dict.items_area.$wrapper;
    $area.html(imx_get_fetch_items_html(items));

    // Live "qty per split" hint
    $area.on('input', '.imx-splits', function () {
        const $input = $(this);
        const index = cint($input.attr('data-idx'));
        const item = items[index] || {};
        const splits = cint($input.val()) || 1;
        $area.find('.imx-qty-split[data-idx="' + index + '"]').text(
            flt(flt(item.qty) / splits, 4) + ' ' + (item.uom || '')
        );
    });

    dialog.show();
}


function imx_get_fetch_items_html(items) {
    let html =
        '<table class="table table-bordered" style="margin-bottom:0;">' +
        '<thead><tr>' +
        '<th style="width:32px;"></th>' +
        '<th>' + __('Item') + '</th>' +
        '<th class="text-right">' + __('Ordered Qty') + '</th>' +
        '<th class="text-right">' + __('Available Barcodes') + '</th>' +
        '<th style="width:90px;">' + __('Splits') + '</th>' +
        '<th class="text-right">' + __('Qty / Split') + '</th>' +
        '<th style="width:190px;">' + __('Transaction ID') + '</th>' +
        '</tr></thead><tbody>';

    items.forEach(function (item, index) {
        const item_code = frappe.utils.escape_html(item.item_code || '');
        const item_name = frappe.utils.escape_html(item.item_name || '');
        const uom = frappe.utils.escape_html(item.uom || '');
        const stock_uom = frappe.utils.escape_html(item.stock_uom || '');

        html +=
            '<tr>' +
            '<td class="text-center">' +
            '<input type="checkbox" class="imx-include" data-idx="' + index + '" checked>' +
            '</td>' +
            '<td>' + item_code +
            (item_name ? '<br><span class="text-muted small">' + item_name + '</span>' : '') +
            (item.has_batch_no ? ' <span class="indicator-pill blue">' + __('Batch') + '</span>' : '') +
            '</td>' +
            '<td class="text-right">' + flt(item.qty, 4) + ' ' + uom +
            '<br><span class="text-muted small">' + flt(item.stock_qty, 4) + ' ' + stock_uom + '</span>' +
            '</td>' +
            '<td class="text-right">' + cint(item.available_barcodes) + '</td>' +
            '<td><input type="number" min="1" step="1" class="form-control imx-splits" ' +
            'data-idx="' + index + '" value="1"></td>' +
            '<td class="text-right"><span class="imx-qty-split" data-idx="' + index + '">' +
            flt(item.qty, 4) + ' ' + uom + '</span></td>' +
            '<td><input type="text" class="form-control imx-transaction-id" ' +
            'data-idx="' + index + '" placeholder="' + __('Transaction ID') + '"></td>' +
            '</tr>';
    });

    html += '</tbody></table>';
    html +=
        '<div class="text-muted small" style="margin-top:8px;">' +
        __('Each split adds one row to the Items table, where you choose the batch barcode. The split qty is a placeholder - the barcode sets the real qty and UOM.') +
        '</div>';

    return html;
}


function imx_add_fetched_items(frm, dialog, items) {
    const $area = dialog.fields_dict.items_area.$wrapper;
    let added = 0;

    items.forEach(function (item, index) {
        const $include = $area.find('.imx-include[data-idx="' + index + '"]');
        if ($include.length && !$include.prop('checked')) {
            return;
        }

        const splits = cint($area.find('.imx-splits[data-idx="' + index + '"]').val());
        if (splits < 1) {
            return;
        }

        const transaction_id = (
            $area.find('.imx-transaction-id[data-idx="' + index + '"]').val() || ''
        ).trim();

        const conversion_factor = flt(item.conversion_factor) || 1;
        const qty_per_split = flt(flt(item.qty) / splits, 4);
        const warehouse = item.warehouse || frm.doc.parent_warehouse;

        for (let i = 0; i < splits; i++) {
            const row = frm.add_child('custom_items');
            row.item_code = item.item_code;
            row.item_name = item.item_name;
            row.warehouse = warehouse;
            row.use_serial_batch_fields = 1;
            // Placeholder qty/UOM; choosing the batch barcode re-fills these
            // from the pack (transaction UOM / stock UOM aware).
            row.uom = item.uom;
            row.stock_uom = item.stock_uom;
            row.conversion_factor = conversion_factor;
            row.qty = qty_per_split;
            row.stock_qty = flt(qty_per_split * conversion_factor, 4);
            row.batch_no = '';
            row.sales_order = frm.doc.custom_sales_order;
            row.sales_order_item = item.sales_order_item;
            row.transaction_id = transaction_id;
            added += 1;
        }
    });

    if (!added) {
        frappe.msgprint(__('Set "Splits" to at least 1 for the items you want to add.'));
        return false;
    }

    frm.refresh_field('custom_items');
    frm.dirty();
    frappe.show_alert({
        message: __('{0} row(s) added. Choose the batch barcode on each row.', [added]),
        indicator: 'green',
    });

    return true;
}

