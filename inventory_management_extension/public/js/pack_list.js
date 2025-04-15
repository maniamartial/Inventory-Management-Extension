frappe.ui.form.on('Pick List', {
    refresh: function(frm) {
        frm.fields_dict["custom_items"].grid.get_field("batch_no").get_query = function(doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            if (!row.item_code || !row.warehouse) return;
            return {
                query: "erpnext.controllers.queries.get_batch_no",
                filters: {
                    item_code: row.item_code,
                    warehouse: row.warehouse
                }
            };
        };

    },
    onload: function(frm, cdt, cdn) {
        items = (frm.doc.custom_items || [])
      
        frm.set_query("barcode", "custom_items", (frm, cdt, cdn) => {
            const row = locals[cdt][cdn];
            const selected_barcodes = items
                .filter(r => r.name !== cdn && r.barcode)
                .map(r => r.barcode);

            return {
                filters: {
                    "item_code": row.item_code,
                    "batch": row.batch_no || undefined,
                    "sold": 0,
                    "name": ["not in", selected_barcodes]
                },
            };
        });
        frm.refresh_field("custom_items");
        frm.refresh();

    }
,    

  
        before_save: function(frm) {
            // if(frm.is_new()){
            //     getSalesOrder(frm);

            // }
            if(frm.is_new() || frm.doc.custom_update_items===1){
            let pick_list_extension = frm.doc.custom_items || [];
    
            if (frm.__last_custom_items_state) {
                let previous_state = JSON.stringify(frm.__last_custom_items_state);
                let current_state = JSON.stringify(pick_list_extension);
    
                if (previous_state === current_state) {
                    console.log("No changes detected in custom_items. Skipping update.");
                    return;
                }
            }
    
            frm.__last_custom_items_state = JSON.parse(JSON.stringify(pick_list_extension));
    
            let grouped_items = {};
    
            pick_list_extension.forEach(row => {
                let key = row.item_code + "-" + (row.batch_no || "NoBatch");
                if (!grouped_items[key]) {
                    grouped_items[key] = {
                        item_code: row.item_code,
                        batch_no: row.batch_no || "NoBatch",
                        warehouse: row.warehouse,
                        qty: 0,
                    };
                }
                grouped_items[key].qty += row.qty;
            });
    
            frm.clear_table("locations");
            Object.values(grouped_items).forEach(data => {
                let new_row = frm.add_child("locations");
                new_row.item_code = data.item_code;
                new_row.use_serial_batch_fields = 1;
                new_row.batch_no = data.batch_no;
                new_row.warehouse = data.warehouse;
                new_row.qty = data.qty;
                new_row.stock_qty = data.qty;
                new_row.picked_qty = data.qty;
            });
            frm.doc.custom_update_items = 0;
            frm.refresh_field("locations"); 
        }
        },
      
        custom_scan_transactional_barcode: function(frm) {
                const barcode = frm.doc.custom_scan_transactional_barcode;
                if (!barcode) return;
        
                frappe.call({
                    method: 'frappe.client.get',
                    args: {
                        doctype: 'Batch Barcode Tracker',
                        name: barcode
                    },
                    callback: function(r) {
                        if (r.message) {
                            const data = r.message;
        
                            const row = frm.add_child('custom_items');
                            row.item_code = data.item_code;
                            row.batch_no = data.batch;
                            row.barcode = data.name;
                            row.qty = data.qty;
                            row.uom = data.uom || 'Nos';
                            row.warehouse = data.warehouse;
        
                            frm.refresh_field('custom_items');
                            frm.set_value('scan_barcode', ''); 
                        } else {
                            frappe.msgprint(`No record found for barcode: ${barcode}`);
                        }
                    }
                });
            }
       

});

frappe.ui.form.on('Pick List Extension', {
    barcode: function(frm, cdt, cdn) {
        let child = locals[cdt][cdn];
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Batch Barcode Tracker',
                filters: { barcode: child.barcode },
                fieldname: ['qty']
            },
            callback: function(response) {
                if (response.message) {
                    let qty = response.message.qty;
                    frappe.model.set_value(cdt, cdn, 'qty', qty);
                } else {
                    frappe.msgprint(__('No such barcode found'));
                }
            }
        });
    },
    package_weight: function(frm, cdt, cdn) {
        update_gross_weight(frm, cdt, cdn);
    },
});

frappe.ui.form.on('Pick List Item', {
    custom_packaging_item: function(frm, cdt, cdn) {
        update_gross_weight_items(frm, cdt, cdn);
    }
});

function update_gross_weight(frm, cdt, cdn) {
    let child_table = frm.doc.custom_items || [];
    
    child_table.forEach(row => {
        if (!row.packaging_item) return;

        if (row.packaging_itemuom === row.stock_uom) {
            let gross_weight = row.qty + row.package_weight;
            frappe.model.set_value(cdt, cdn, 'gross_weight', gross_weight);
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
                        let converted_qty = row.qty * conversion_factor; // Convert quantity
                        let gross_weight = converted_qty + row.package_weight;
                        frappe.model.set_value(cdt, cdn, 'gross_weight', gross_weight);
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
        if (!row.custom_packaging_item) return;

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
                    if (r.message && r.message.conversion_factor) {
                        let conversion_factor = r.message.conversion_factor;
                        let converted_qty = row.stock_qty * conversion_factor; // Convert quantity
                        let gross_weight = converted_qty + row.custom_packing_weight;
                        frappe.model.set_value(cdt, cdn, 'custom_gross_weight', gross_weight);
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
