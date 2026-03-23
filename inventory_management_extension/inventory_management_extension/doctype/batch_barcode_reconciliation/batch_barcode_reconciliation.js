// Copyright (c) 2026, nei and contributors
// For license information, please see license.txt

frappe.provide("erpnext.stock");
frappe.provide("erpnext.accounts.dimensions");

frappe.ui.form.on("Batch Barcode Reconciliation", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = ["Serial and Batch Bundle"];
		frm.barcode_scanner = new erpnext.utils.BarcodeScanner({
			frm: frm,
			uom_field: "stock_uom",
		});
	},

	onload: function (frm) {
		frm.add_fetch("item_code", "item_name", "item_name");

		// end of life
		frm.set_query("item_code", "items", function (doc, cdt, cdn) {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters: {
					is_stock_item: 1,
				},
			};
		});
		frm.set_query("batch_no", "items", function (doc, cdt, cdn) {
			var item = locals[cdt][cdn];
			return {
				filters: {
					item: item.item_code,
				},
			};
		});

		frm.set_query("serial_and_batch_bundle", "items", (doc, cdt, cdn) => {
			let row = locals[cdt][cdn];
			return {
				filters: {
					item_code: row.item_code,
					voucher_type: doc.doctype,
					voucher_no: ["in", [doc.name, ""]],
					is_cancelled: 0,
				},
			};
		});

		let sbb_field = frm.get_docfield("items", "serial_and_batch_bundle");
		if (sbb_field) {
			sbb_field.get_route_options_for_new_doc = (row) => {
				return {
					item_code: row.doc.item_code,
					warehouse: row.doc.warehouse,
					voucher_type: frm.doc.doctype,
				};
			};
		}

		if (frm.doc.company) {
			erpnext.queries.setup_queries(frm, "Warehouse", function () {
				return erpnext.queries.warehouse(frm.doc);
			});
		}

		if (!frm.doc.expense_account) {
			frm.trigger("set_expense_account");
		}

		erpnext.accounts.dimensions.setup_dimension_filters(frm, frm.doctype);
	},

	company: function (frm) {
		frm.trigger("toggle_display_account_head");
		erpnext.accounts.dimensions.update_dimension(frm, frm.doctype);
	},

	refresh: function (frm) {
		if (frm.doc.docstatus < 1) {
			// Fetch group: all fetch-related actions under one dropdown
			frm.add_custom_button(__("Fetch Items from Warehouse"), function () {
				frm.events.get_items(frm);
			}, __("Action"));
			frm.add_custom_button(__("Fetch Missing Batch Barcodes"), function () {
				frm.events.fetch_missing_batch_barcodes(frm);
			}, __("Action"));
			frm.add_custom_button(__("Add Missing to Items"), function () {
				frm.events.add_missing_to_items(frm);
			}, __("Action"));
			// Create group: Stock Entry from new barcodes and from missing barcodes
			frm.add_custom_button(__("Create Stock Entry (Material Receipt)"), function () {
				frm.events.create_material_receipt_from_new_barcodes(frm);
			}, __("Create"));
			frm.add_custom_button(__("Create Stock Entry (Material Issue)"), function () {
				frm.events.create_material_issue_from_missing_barcodes(frm);
			}, __("Create"));
		}

		// Create group when submitted: Stock Reconciliation
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Stock Reconciliation"), function () {
				frm.events.convert_to_stock_reconciliation(frm);
			}, __("Create"));
			frm.add_custom_button(__("Create Stock Entry (Material Receipt)"), function () {
				frm.events.create_material_receipt_from_new_barcodes(frm);
			}, __("Create"));
		}

		if (frm.doc.company) {
			frm.trigger("toggle_display_account_head");
		}

		frm.events.set_fields_onload_for_line_item(frm);
	},

	fetch_missing_batch_barcodes: function (frm) {
		frappe.call({
			method: "inventory_management_extension.inventory_management_extension.doctype.batch_barcode_reconciliation.batch_barcode_reconciliation.get_missing_batch_barcodes",
			args: { doc: frm.doc },
			callback: function (r) {
				if (r.exc || !r.message || !r.message.length) {
					frappe.msgprint(__("No missing batch barcodes. All trackers for each batch and warehouse are already in Items."));
					return;
				}
				frm.clear_table("missing_batch_barcodes");
				r.message.forEach(function (row) {
					let child = frm.add_child("missing_batch_barcodes");
					child.barcode = row.barcode;
					child.qty = row.qty;
					child.batch = row.batch;
					child.warehouse = row.warehouse;
				});
				frm.refresh_field("missing_batch_barcodes");
				frappe.show_alert({ message: __("Fetched {0} missing barcode(s). Add them to Items using 'Add Missing to Items'.", [r.message.length]), indicator: "blue" });
			},
		});
	},

	add_missing_to_items: function (frm) {
		if (!frm.doc.missing_batch_barcodes || !frm.doc.missing_batch_barcodes.length) {
			frappe.msgprint(__("No rows in Missing Batch Barcodes. Use 'Fetch Missing Batch Barcodes' first."));
			return;
		}
		frm.save().then(function () {
			frappe.call({
				method: "inventory_management_extension.inventory_management_extension.doctype.batch_barcode_reconciliation.batch_barcode_reconciliation.add_missing_batch_barcodes_to_items",
				args: { doc_name: frm.doc.name },
				callback: function (r) {
					if (!r.exc && r.message) {
						frm.reload_doc().then(function () {
							frm.trigger("set_valuation_rate_and_qty_for_all_items");
						});
						frappe.msgprint(r.message.message || __("Added missing barcodes to Items."));
					}
				},
			});
		});
	},

	create_material_receipt_from_new_barcodes: function (frm) {
		if (!frm.doc.new_barcodes || !frm.doc.new_barcodes.length) {
			frappe.msgprint(__("No rows in New Barcodes. Scan unknown barcodes first."));
			return;
		}
		frappe.call({
			method: "inventory_management_extension.inventory_management_extension.doctype.batch_barcode_reconciliation.batch_barcode_reconciliation.create_material_receipt_from_new_barcodes",
			args: { doc_name: frm.doc.name },
			callback: function (r) {
				if (!r.exc && r.message && r.message.stock_entry) {
					frappe.msgprint({ message: r.message.message, indicator: "green" });
					frappe.set_route("Form", "Stock Entry", r.message.stock_entry);
				}
			},
		});
	},

	create_material_issue_from_missing_barcodes: function (frm) {
		if (!frm.doc.missing_batch_barcodes || !frm.doc.missing_batch_barcodes.length) {
			frappe.msgprint(__("No rows in Missing Batch Barcodes. Use 'Fetch Missing Batch Barcodes' first."));
			return;
		}
		function do_create() {
			frappe.call({
				method: "inventory_management_extension.inventory_management_extension.doctype.batch_barcode_reconciliation.batch_barcode_reconciliation.create_material_issue_from_missing_barcodes",
				args: { doc_name: frm.doc.name },
				callback: function (r) {
					if (!r.exc && r.message && r.message.stock_entry) {
						frappe.msgprint({ message: r.message.message, indicator: "green" });
						frappe.set_route("Form", "Stock Entry", r.message.stock_entry);
					}
				},
			});
		}
		// Save only if there are unsaved changes (avoid "No changes in document")
		if (frm.is_dirty()) {
			frm.save().then(do_create);
		} else {
			do_create();
		}
	},

	set_fields_onload_for_line_item(frm) {
		if (frm.is_new() && frm.doc?.items && cint(frappe.user_defaults?.use_serial_batch_fields) === 1) {
			frm.doc.items.forEach((item) => {
				if (!item.serial_and_batch_bundle) {
					frappe.model.set_value(item.doctype, item.name, "use_serial_batch_fields", 1);
				}
			});
		}
	},

	convert_to_stock_reconciliation: function (frm) {
		// Bundle items by batch and warehouse (same as Stock Reconciliation)
		const bundled_items = {};
		
		frm.doc.items.forEach(function (item) {
			// Create key: batch_no + warehouse (same bundling as Stock Reconciliation)
			const key = item.batch_no + "|" + item.warehouse;
			
			if (!bundled_items[key]) {
				bundled_items[key] = {
					item_code: item.item_code,
					item_name: item.item_name,
					batch_no: item.batch_no,
					warehouse: item.warehouse,
					qty: 0,
					current_qty: 0,
					valuation_rate: 0,
					current_valuation_rate: 0,
					serial_and_batch_bundle: item.serial_and_batch_bundle,
					use_serial_batch_fields: item.use_serial_batch_fields,
				};
			}
			
			// Sum quantities for same batch+warehouse
			bundled_items[key].qty += flt(item.qty);
			bundled_items[key].current_qty += flt(item.current_qty);
			bundled_items[key].valuation_rate = item.valuation_rate;  // Use last value
			bundled_items[key].current_valuation_rate = item.current_valuation_rate;
		});
		
		// Prepare items array
		const items = Object.values(bundled_items);
		
		if (items.length === 0) {
			frappe.msgprint(__("No items to convert"));
			return;
		}
		
		// Create Stock Reconciliation document
		frappe.call({
			method: "frappe.client.insert",
			args: {
				doc: {
					doctype: "Stock Reconciliation",
					company: frm.doc.company,
					purpose: frm.doc.purpose || "Stock Reconciliation",
					posting_date: frm.doc.posting_date,
					posting_time: frm.doc.posting_time,
					set_warehouse: frm.doc.set_warehouse,
					items: items.map(function (item) {
						return {
							doctype: "Stock Reconciliation Item",
							item_code: item.item_code,
							item_name: item.item_name,
							batch_no: item.batch_no,
							warehouse: item.warehouse,
							qty: item.qty,
							current_qty: item.current_qty,
							valuation_rate: item.valuation_rate,
							current_valuation_rate: item.current_valuation_rate,
							serial_and_batch_bundle: item.serial_and_batch_bundle,
							use_serial_batch_fields: item.use_serial_batch_fields,
						};
					}),
				},
			},
			callback: function (r) {
				if (!r.exc) {
					frappe.msgprint({
						message: __("Stock Reconciliation created successfully"),
						indicator: "green",
						title: __("Success"),
					});
					
					// Open the created Stock Reconciliation
					frappe.set_route("Form", "Stock Reconciliation", r.message.name);
				}
			},
		});
	},

	scan_barcode: function (frm) {
		const scanned_barcode = frm.doc.scan_barcode;
		
		if (!scanned_barcode) {
			return;
		}

		function add_barcode_to_new_barcodes() {
			const existing = (frm.doc.new_barcodes || []).find(function (row) { return row.barcode === scanned_barcode; });
			if (existing) {
				frappe.show_alert({ message: __("Barcode '{0}' already in New Barcodes.", [scanned_barcode]), indicator: "yellow" });
			} else {
				let row = frm.add_child("new_barcodes");
				row.barcode = scanned_barcode;
				row.qty = 1;
				row.warehouse = frm.doc.set_warehouse || "";
				frm.refresh_field("new_barcodes");
				frappe.show_alert({ message: __("Barcode '{0}' added to New Barcodes. Set Item Code and use 'Create Stock Entry (Material Receipt)' when ready.", [scanned_barcode]), indicator: "blue" });
			}
			frm.set_value("scan_barcode", "");
		}

		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "Batch Barcode Tracker",
				name: scanned_barcode,
			},
			callback: function (r) {
				if (r.message) {
					const tracker = r.message;
					frm.events.process_batch_barcode_scan(frm, tracker);
					frm.set_value("scan_barcode", "");
				} else if (r.exc) {
					// Server error (e.g. "Batch Barcode Tracker X not found"): treat as new barcode
					add_barcode_to_new_barcodes();
				} else {
					add_barcode_to_new_barcodes();
				}
			},
			error: function () {
				// Network/request error or doc not found: still add to New Barcodes
				add_barcode_to_new_barcodes();
			},
		});
	},

	process_batch_barcode_scan: function (frm, tracker) {
		// Check if item is marked as sold (balance = 0)
		if (tracker.sold === 1 || cint(tracker.sold) === 1) {
			frappe.msgprint({
				title: __("Item Already Sold"),
				message: __("This item (Barcode: {0}) is marked as SOLD with balance = 0. Cannot add to reconciliation.", [tracker.barcode]),
				indicator: "red",
			});
			frm.set_value("scan_barcode", "");
			return;  // Stop processing
		}

		// Check if warehouse is set, if not set it from tracker
		if (!frm.doc.set_warehouse && tracker.warehouse) {
			frm.set_value("set_warehouse", tracker.warehouse);
		}

		// Check if an item with the same barcode already exists
		const existing_item = frm.doc.items.find((item) => item.batch_barcode === tracker.name);

		if (existing_item) {
			// Keep current_qty = original tracker qty; only reconciled qty increases
			const new_qty = flt(existing_item.qty) + flt(tracker.qty);
			frappe.model.set_value(existing_item.doctype, existing_item.name, "qty", new_qty);
			frm.events.set_amount_quantity(frm.doc, existing_item.doctype, existing_item.name);

			frappe.show_alert({
				message: __("Item updated. Quantity increased by {0}", [tracker.qty]),
				indicator: "yellow",
			});
		} else {
			// Add a new row for this barcode
			let item = frm.add_child("items");
			item.barcode = tracker.barcode;
			item.item_code = tracker.item_code;
			item.warehouse = tracker.warehouse || frm.doc.set_warehouse;
			item.batch_no = tracker.batch;
			item.batch_barcode = tracker.name;
			item.qty = flt(tracker.qty) || 0;
			item.stock_uom = tracker.uom;

			// Enable use_serial_batch_fields if batch is present
			if (tracker.batch) {
				item.use_serial_batch_fields = 1;
			}

			frm.refresh_field("items");

			// current_qty from Batch Barcode Tracker; valuation from stock (rate only)
			frm.events.sync_qty_from_tracker_and_valuation(frm, item.doctype, item.name, tracker);

			frappe.show_alert({
				message: __("Barcode '{0}' scanned successfully. Item added to the list.", [tracker.barcode]),
				indicator: "green",
			});
		}

		// Update last scanned warehouse
		if (tracker.warehouse) {
			frm.set_value("last_scanned_warehouse", tracker.warehouse);
		}
	},

	scan_mode: function (frm) {
		if (frm.doc.scan_mode) {
			frappe.show_alert({
				message: __("Scan mode enabled, existing quantity will not be fetched."),
				indicator: "green",
			});
		}
	},

	set_warehouse: function (frm) {
		let transaction_controller = new erpnext.TransactionController({ frm: frm });
		transaction_controller.autofill_warehouse(frm.doc.items, "warehouse", frm.doc.set_warehouse);
	},

	get_items: function (frm) {
		let fields = [
			{
				label: "Warehouse",
				fieldname: "warehouse",
				fieldtype: "Link",
				options: "Warehouse",
				reqd: 1,
				get_query: function () {
					return {
						filters: {
							company: frm.doc.company,
						},
					};
				},
			},
			{
				label: "Item Code",
				fieldname: "item_code",
				fieldtype: "Link",
				options: "Item",
			},
			{
				label: __("Ignore Empty Stock"),
				fieldname: "ignore_empty_stock",
				fieldtype: "Check",
			},
		];

		frappe.prompt(
			fields,
			function (data) {
				frappe.call({
					method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_items",
					args: {
						warehouse: data.warehouse,
						posting_date: frm.doc.posting_date,
						posting_time: frm.doc.posting_time,
						company: frm.doc.company,
						item_code: data.item_code,
						ignore_empty_stock: data.ignore_empty_stock,
					},
					callback: function (r) {
						if (r.exc || !r.message || !r.message.length) return;

						frm.clear_table("items");

						r.message.forEach((row) => {
							let item = frm.add_child("items");
							$.extend(item, row);

							item.qty = item.qty || 0;
							item.valuation_rate = item.valuation_rate || 0;
							item.use_serial_batch_fields = cint(
								frappe.user_defaults?.use_serial_batch_fields
							);
						});
						frm.refresh_field("items");
					},
				});
			},
			__("Get Items"),
			__("Update")
		);
	},

	posting_date: function (frm) {
		frm.trigger("set_valuation_rate_and_qty_for_all_items");
	},

	posting_time: function (frm) {
		frm.trigger("set_valuation_rate_and_qty_for_all_items");
	},

	set_valuation_rate_and_qty_for_all_items: function (frm) {
		frm.doc.items.forEach((row) => {
			if (row.batch_barcode) {
				frm.events.sync_qty_from_tracker_and_valuation(frm, row.doctype, row.name, null);
			} else {
				frm.events.set_valuation_rate_and_qty(frm, row.doctype, row.name);
			}
		});
	},

	/**
	 * For lines with Batch Barcode Tracker: current_qty = tracker.qty (not stock balance).
	 * quantity_difference = reconciled qty - tracker qty. Valuation rate still from get_stock_balance_for.
	 */
	sync_qty_from_tracker_and_valuation: function (frm, cdt, cdn, tracker_doc) {
		const row = frappe.model.get_doc(cdt, cdn);
		if (!row.batch_barcode || !row.item_code || !row.warehouse) {
			frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
			return;
		}

		function apply_tracker_then_rate(t) {
			const tracker_qty = flt(t.qty) || 0;
			frappe.model.set_value(cdt, cdn, "current_qty", tracker_qty);
			const drow = frappe.model.get_doc(cdt, cdn);
			frappe.call({
				method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
				args: {
					item_code: drow.item_code,
					warehouse: drow.warehouse,
					posting_date: frm.doc.posting_date,
					posting_time: frm.doc.posting_time,
					batch_no: drow.batch_no,
					row: drow,
					company: frm.doc.company,
				},
				callback: function (r) {
					if (!r || !r.message) {
						return;
					}
					const d = frappe.model.get_doc(cdt, cdn);
					const rate = flt(r.message.rate) || 0;
					const cur_qty = flt(d.current_qty) || 0;
					frappe.model.set_value(cdt, cdn, "valuation_rate", rate);
					frappe.model.set_value(cdt, cdn, "current_valuation_rate", rate);
					frappe.model.set_value(cdt, cdn, "current_amount", rate * cur_qty);
					frappe.model.set_value(cdt, cdn, "amount", flt(d.qty) * rate);
					frappe.model.set_value(cdt, cdn, "current_serial_no", r.message.serial_nos || "");
					frappe.model.set_value(
						cdt,
						cdn,
						"use_serial_batch_fields",
						cint(r.message.use_serial_batch_fields)
					);
					if (frm.doc.purpose == "Stock Reconciliation" && !frm.doc.scan_mode) {
						frappe.model.set_value(cdt, cdn, "serial_no", r.message.serial_nos || "");
					}
					frm.events.set_amount_quantity(frm.doc, cdt, cdn);
				},
			});
		}

		if (tracker_doc) {
			apply_tracker_then_rate(tracker_doc);
		} else {
			frappe.call({
				method: "frappe.client.get",
				args: { doctype: "Batch Barcode Tracker", name: row.batch_barcode },
				callback: function (r) {
					if (r.message) {
						apply_tracker_then_rate(r.message);
					} else {
						// Invalid tracker link: use stock ledger qty (avoid recursion with batch_barcode branch)
						frm.events.set_valuation_from_stock_balance_only(frm, cdt, cdn);
					}
				},
			});
		}
	},

	/** Same as legacy stock reconciliation row fetch: current_qty from get_stock_balance (no tracker). */
	set_valuation_from_stock_balance_only: function (frm, cdt, cdn) {
		const d = frappe.model.get_doc(cdt, cdn);
		if (!d.item_code || !d.warehouse) {
			return;
		}
		frappe.call({
			method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
			args: {
				item_code: d.item_code,
				warehouse: d.warehouse,
				posting_date: frm.doc.posting_date,
				posting_time: frm.doc.posting_time,
				batch_no: d.batch_no,
				row: d,
				company: frm.doc.company,
			},
			callback: function (r) {
				if (!r || !r.message) {
					return;
				}
				const row = frappe.model.get_doc(cdt, cdn);
				if (!frm.doc.scan_mode) {
					frappe.model.set_value(cdt, cdn, "qty", r.message.qty);
				}
				frappe.model.set_value(cdt, cdn, "valuation_rate", r.message.rate);
				frappe.model.set_value(cdt, cdn, "current_qty", r.message.qty);
				frappe.model.set_value(cdt, cdn, "current_valuation_rate", r.message.rate);
				frappe.model.set_value(cdt, cdn, "current_amount", r.message.rate * r.message.qty);
				frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(r.message.rate));
				frappe.model.set_value(cdt, cdn, "current_serial_no", r.message.serial_nos);
				frappe.model.set_value(
					cdt,
					cdn,
					"use_serial_batch_fields",
					r.message.use_serial_batch_fields
				);
				if (frm.doc.purpose == "Stock Reconciliation" && !frm.doc.scan_mode) {
					frappe.model.set_value(cdt, cdn, "serial_no", r.message.serial_nos);
				}
				frm.events.set_amount_quantity(frm.doc, cdt, cdn);
			},
		});
	},

	/** Lines without batch_barcode: use ERPNext stock balance for current_qty (e.g. Fetch Items from Warehouse). */
	set_valuation_rate_and_qty: function (frm, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);

		if (d.batch_barcode) {
			frm.events.sync_qty_from_tracker_and_valuation(frm, cdt, cdn, null);
			return;
		}

		if (d.item_code && d.warehouse) {
			frappe.call({
				method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
				args: {
					item_code: d.item_code,
					warehouse: d.warehouse,
					posting_date: frm.doc.posting_date,
					posting_time: frm.doc.posting_time,
					batch_no: d.batch_no,
					row: d,
					company: frm.doc.company,
				},
				callback: function (r) {
					const row = frappe.model.get_doc(cdt, cdn);
					if (!frm.doc.scan_mode) {
						frappe.model.set_value(cdt, cdn, "qty", r.message.qty);
					}
					frappe.model.set_value(cdt, cdn, "valuation_rate", r.message.rate);
					frappe.model.set_value(cdt, cdn, "current_qty", r.message.qty);
					frappe.model.set_value(cdt, cdn, "current_valuation_rate", r.message.rate);
					frappe.model.set_value(cdt, cdn, "current_amount", r.message.rate * r.message.qty);
					frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(r.message.rate));
					frappe.model.set_value(cdt, cdn, "current_serial_no", r.message.serial_nos);
					frappe.model.set_value(
						cdt,
						cdn,
						"use_serial_batch_fields",
						r.message.use_serial_batch_fields
					);

					if (frm.doc.purpose == "Stock Reconciliation" && !frm.doc.scan_mode) {
						frappe.model.set_value(cdt, cdn, "serial_no", r.message.serial_nos);
					}
					frm.events.set_amount_quantity(frm.doc, cdt, cdn);
				},
			});
		}
	},

	set_amount_quantity: function (doc, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);
		frappe.model.set_value(cdt, cdn, "quantity_difference", flt(d.qty) - flt(d.current_qty));
		const vr = flt(d.valuation_rate);
		const cur_vr = flt(d.current_valuation_rate);
		frappe.model.set_value(cdt, cdn, "amount", flt(d.qty) * vr);
		frappe.model.set_value(cdt, cdn, "current_amount", flt(d.current_qty) * cur_vr);
		frappe.model.set_value(cdt, cdn, "amount_difference", flt(d.amount) - flt(d.current_amount));
	},
	toggle_display_account_head: function (frm) {
		frm.toggle_display(
			["expense_account", "cost_center"],
			erpnext.is_perpetual_inventory_enabled(frm.doc.company)
		);
	},
	purpose: function (frm) {
		frm.trigger("set_expense_account");
	},
	set_expense_account: function (frm) {
		if (frm.doc.company && erpnext.is_perpetual_inventory_enabled(frm.doc.company)) {
			return frm.call({
				method: "erpnext.stock.doctype.stock_reconciliation.stock_reconciliation.get_difference_account",
				args: {
					purpose: frm.doc.purpose,
					company: frm.doc.company,
				},
				callback: function (r) {
					if (!r.exc) {
						frm.set_value("expense_account", r.message);
					}
				},
			});
		}
	},

	// Batch Barcode Tracker update (qty + single transaction per item) is done server-side only in on_submit (batch_barcode_reconciliation.py)
	// to avoid creating duplicate transaction records.
});

frappe.ui.form.on("Batch Barcode Reconciliation Item", {
	// Ensure batch_barcode is saved when set
	batch_barcode: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.batch_barcode && row.item_code && row.warehouse) {
			frm.events.sync_qty_from_tracker_and_valuation(frm, cdt, cdn, null);
		}
	},

	warehouse: function (frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		if (child.batch_no && !frm.doc.scan_mode) {
			frappe.model.set_value(child.cdt, child.cdn, "batch_no", "");
		}

		frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
	},

	item_code: function (frm, cdt, cdn) {
		var child = locals[cdt][cdn];
		if (child.batch_no && !frm.doc.scan_mode) {
			frappe.model.set_value(cdt, cdn, "batch_no", "");
		}

		frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
	},

	batch_no(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.batch_no) {
			frappe.model.set_value(cdt, cdn, {
				use_serial_batch_fields: 1,
				serial_and_batch_bundle: "",
			});

			frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
		}
	},

	qty: function (frm, cdt, cdn) {
		frm.events.set_amount_quantity(frm, cdt, cdn);

		let row = locals[cdt][cdn];
		if (row.use_serial_batch_fields && !row.qty && row.serial_no) {
			frappe.model.set_value(cdt, cdn, "serial_no", "");
		}
	},

	valuation_rate: function (frm, cdt, cdn) {
		frm.events.set_amount_quantity(frm, cdt, cdn);
	},

	serial_no: function (frm, cdt, cdn) {
		var child = locals[cdt][cdn];

		if (child.serial_no) {
			frappe.model.set_value(cdt, cdn, {
				use_serial_batch_fields: 1,
				serial_and_batch_bundle: "",
			});

			const serial_nos = child.serial_no.trim().split("\n");
			frappe.model.set_value(cdt, cdn, "qty", serial_nos.length);
		}
	},

	items_add: function (frm, cdt, cdn) {
		var item = frappe.get_doc(cdt, cdn);
		if (!item.warehouse && frm.doc.set_warehouse) {
			frappe.model.set_value(cdt, cdn, "warehouse", frm.doc.set_warehouse);
		}

		if (item.docstatus === 0 && cint(frappe.user_defaults?.use_serial_batch_fields) === 1) {
			frappe.model.set_value(item.doctype, item.name, "use_serial_batch_fields", 1);
		}
	},

	add_serial_batch_bundle(frm, cdt, cdn) {
		erpnext.utils.pick_serial_and_batch_bundle(frm, cdt, cdn, "Inward");
	},
});

erpnext.stock.StockReconciliation = class StockReconciliation extends erpnext.stock.StockController {
	setup() {
		var me = this;

		this.setup_posting_date_time_check();

		if (me.frm.doc.company && erpnext.is_perpetual_inventory_enabled(me.frm.doc.company)) {
			this.frm.add_fetch("company", "cost_center", "cost_center");
		}
		this.frm.fields_dict["expense_account"].get_query = function () {
			if (erpnext.is_perpetual_inventory_enabled(me.frm.doc.company)) {
				return {
					filters: {
						company: me.frm.doc.company,
						is_group: 0,
					},
				};
			}
		};
		this.frm.fields_dict["cost_center"].get_query = function () {
			if (erpnext.is_perpetual_inventory_enabled(me.frm.doc.company)) {
				return {
					filters: {
						company: me.frm.doc.company,
						is_group: 0,
					},
				};
			}
		};
	}

	refresh() {
		if (this.frm.doc.docstatus > 0) {
			this.show_stock_ledger();
			erpnext.utils.view_serial_batch_nos(this.frm);
			if (erpnext.is_perpetual_inventory_enabled(this.frm.doc.company)) {
				this.show_general_ledger();
			}
		}
	}
};

cur_frm.cscript = new erpnext.stock.StockReconciliation({ frm: cur_frm });