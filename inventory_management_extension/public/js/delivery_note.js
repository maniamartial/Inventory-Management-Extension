frappe.ui.form.on('Delivery Note', {
    custom_batch_barcode: function(frm) {
        if (!frm.doc.custom_batch_barcode || frm.doc.custom_batch_barcode.length === 0) {
            return;
        }
        
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.utils.get_total_qty_from_barcodes",
            args: {
                barcode: frm.doc.custom_batch_barcode,
            },
            callback: function(response) {
                if (response.message) {
                    let item_qty_map = response.message;
                    
                    frm.doc.items.forEach(row => {
                        
                            frappe.model.set_value(row.doctype, row.name, "qty", item_qty_map);
                        
                    });

                    frm.refresh_field("items");
                }
            }
        });
    }
});
frappe.ui.form.on('Delivery Note', {
    refresh: function(frm) {
        setup_barcode_filters(frm);
    },
    items_add: function(frm) {
        setup_barcode_filters(frm);
    }
});

frappe.ui.form.on('Delivery Note Item', {
    batch_no: function(frm, cdt, cdn) {
        setup_barcode_filters(frm);
    }
});

function setup_barcode_filters(frm) {
    if (!frm.fields_dict.custom_batch_barcode || !frm.doc.items || frm.doc.items.length === 0) {
        return;
    }

    const first_item = frm.doc.items[0];
    const batch_no = first_item.batch_no;
    const item_code = first_item.item_code;

    frm.set_query('custom_batch_barcode', function() {
        let filters = {};
        
        if (batch_no) {
            filters['batch'] = batch_no;
        }
        if (item_code) {
            filters['item_code'] = item_code;
        }

        return {
            filters: filters
        };
    });

    frm.refresh_field('custom_batch_barcode');
}