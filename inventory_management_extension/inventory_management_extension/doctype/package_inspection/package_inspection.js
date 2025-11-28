// Copyright (c) 2025, nei and contributors
// For license information, please see license.txt

frappe.ui.form.on("Package Inspection", {
	refresh(frm) {
		// Set focus on barcode field for automatic scanning
		if (frm.doc.scan_barcode && frm.fields_dict.scan_barcode) {
			frm.fields_dict.scan_barcode.set_focus();
		}
		
		setup_automatic_barcode_detection(frm);
	},
	
	scan_barcode(frm) {
		if (frm.doc.scan_barcode) {
			process_barcode_scan(frm);
		}
	}
});

// Function to setup automatic barcode detection
function setup_automatic_barcode_detection(frm) {
	// Remove any existing listeners
	$(document).off('keypress.package_inspection');
	
	// Add listener for automatic barcode detection
	$(document).on('keypress.package_inspection', function(e) {
		// Check if we're on the package inspection form
		if (cur_frm && cur_frm.doctype === "Package Inspection" && cur_frm.docname === frm.doc.name) {
			// Check if barcode field is focused
			let barcode_field = $('[data-fieldname="scan_barcode"] input');
			if (barcode_field.is(':focus')) {
				// Handle barcode input when Enter is pressed
				if (e.which === 13) { // Enter key pressed
					e.preventDefault();
					let current_value = $(e.target).val();
					if (current_value && current_value.length > 0) {
						frm.set_value("scan_barcode", current_value);
						process_barcode_scan(frm);
					}
				}
			}
		}
	});
}

// Function to process barcode scan
function process_barcode_scan(frm) {
	let barcode = frm.doc.scan_barcode;
	
	if (!barcode) return;
	
	// Clear the barcode field immediately for next scan
	frm.set_value("scan_barcode", "");
	
	// Call server method to get package details
	frappe.call({
		method: "inventory_management_extension.inventory_management_extension.doctype.package_inspection.package_inspection.get_package_details_by_barcode",
		args: {
			barcode: barcode
		},
		callback: function(r) {
			if (r.message) {
				display_package_details_modal(r.message);
			} else {
				frappe.msgprint({
					title: __("Package Not Found"),
					message: __("No package found for barcode: {0}", [barcode]),
					indicator: "orange"
				});
			}
			
			// Set focus back to barcode field for next scan
			setTimeout(function() {
				if (frm.fields_dict.scan_barcode) {
					frm.fields_dict.scan_barcode.set_focus();
				}
			}, 100);
		}
	});
}

// Function to display package details in a modal
function display_package_details_modal(data) {
	let dialog = new frappe.ui.Dialog({
		title: __("Package Verification Details"),
		fields: [
			{
				fieldtype: "Section Break",
				label: __("Package Information")
			},
			{
				fieldname: "barcode",
				fieldtype: "Data",
				label: __("Barcode"),
				default: data.barcode,
				read_only: 1
			},
			{
				fieldname: "column_break_1",
				fieldtype: "Column Break"
			},
			{
				fieldname: "product_code",
				fieldtype: "Data",
				label: __("Product Code"),
				default: data.product_code,
				read_only: 1
			},
			{
				fieldname: "section_break_1",
				fieldtype: "Section Break"
			},
			{
				fieldname: "product_name",
				fieldtype: "Data",
				label: __("Product Name"),
				default: data.product_name,
				read_only: 1
			},
			{
				fieldname: "column_break_2",
				fieldtype: "Column Break"
			},
			{
				fieldname: "batch_number",
				fieldtype: "Data",
				label: __("Batch Number"),
				default: data.batch_number,
				read_only: 1
			},
			{
				fieldname: "section_break_2",
				fieldtype: "Section Break"
			},
			{
				fieldname: "date_of_manufacture",
				fieldtype: "Date",
				label: __("Date of Manufacture"),
				default: data.date_of_manufacture,
				read_only: 1
			},
			{
				fieldname: "column_break_3",
				fieldtype: "Column Break"
			},
			{
				fieldname: "warehouse_location",
				fieldtype: "Data",
				label: __("Warehouse Location"),
				default: data.warehouse_location,
				read_only: 1
			},
			{
				fieldname: "section_break_3",
				fieldtype: "Section Break"
			},
			{
				fieldname: "qty",
				fieldtype: "Float",
				label: __("Quantity"),
				default: data.qty,
				read_only: 1
			},
			{
				fieldname: "column_break_4",
				fieldtype: "Column Break"
			},
			{
				fieldname: "uom",
				fieldtype: "Data",
				label: __("Unit of Measure"),
				default: data.uom,
				read_only: 1
			},
			{
				fieldname: "section_break_4",
				fieldtype: "Section Break"
			},
			{
				fieldname: "sold_status",
				fieldtype: "Data",
				label: __("Status"),
				default: data.sold ? __("Sold") : __("Available"),
				read_only: 1
			}
		],
		primary_action_label: __("Close"),
		primary_action: function() {
			dialog.hide();
		}
	});
	
	// Style the primary action button (Close button) with the same color as header
	setTimeout(function() {
		dialog.$wrapper.find('.modal-footer .btn-primary').css({
			'background-color': '#A9D487',
			'border-color': '#A9D487',
			'color': '#2c3e50',
			'font-weight': '600',
			'padding': '8px 20px'
		});
		
		// Add hover effect for the button
		dialog.$wrapper.find('.modal-footer .btn-primary').hover(
			function() {
				$(this).css({
					'background-color': '#95C170',
					'border-color': '#95C170'
				});
			},
			function() {
				$(this).css({
					'background-color': '#A9D487',
					'border-color': '#A9D487'
				});
			}
		);
	}, 100);
	
	// Add custom styling for better visibility
	dialog.$wrapper.find('.modal-body').css({
		'font-size': '14px',
		'padding': '20px'
	});
	
	// Style the modal header with custom background color
	dialog.$wrapper.find('.modal-header').css({
		'background-color': '#A9D487',
		'color': '#2c3e50',
		'padding': '15px 20px',
		'border-radius': '4px 4px 0 0',
		'font-weight': '600'
	});
	
	// Style the modal title
	dialog.$wrapper.find('.modal-title').css({
		'color': '#2c3e50',
		'font-size': '18px',
		'font-weight': '600'
	});
	
	// Style the close button to be visible on the colored header
	dialog.$wrapper.find('.modal-header .close').css({
		'color': '#2c3e50',
		'opacity': '0.8',
		'font-size': '24px',
		'font-weight': 'bold'
	});
	
	// Add hover effect for close button
	dialog.$wrapper.find('.modal-header .close').hover(
		function() {
			$(this).css('opacity', '1');
		},
		function() {
			$(this).css('opacity', '0.8');
		}
	);
	
	// Highlight sold items
	if (data.sold) {
		dialog.$wrapper.find('[data-fieldname="sold_status"]').closest('.form-group')
			.find('input').css('color', 'red');
	}
	
	// Add subtle border to modal for better definition
	dialog.$wrapper.find('.modal-content').css({
		'border': 'none',
		'box-shadow': '0 4px 6px rgba(0, 0, 0, 0.1)'
	});
	
	dialog.show();
}
