frappe.ui.form.on('Purchase Receipt', {
    
    custom_split_items: function(frm) {
      split_iems_(frm);
    },

    refresh: function(frm) {
        frm.add_custom_button(__('Split Items'), function() {
            split_iems_(frm);
        });
    }
});

function split_iems_(frm){
    let has_split = frm.doc.items.some(item => item.custom_split_no > 1);
    if (has_split) {
        frappe.call({
            method: "inventory_management_extension.inventory_management_extension.utils.split_purchase_receipt_items",
            args: {
                purchase_receipt: frm.doc.name,
            },
            callback: function(r) {
                if (r.message) {
                    frm.refresh();
                    frappe.show_alert({
                        message: __('Items successfully split'),
                        indicator: 'green'
                    });
                }
            },
            freeze: true,
            freeze_message: __('Splitting items...')
        });
    } else {
        frappe.msgprint(__('Please set split count greater than 1 for this item.'));
    }
}