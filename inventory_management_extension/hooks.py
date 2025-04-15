app_name = "inventory_management_extension"
app_title = "Inventory Management Extension"
app_publisher = "nei"
app_description = "Inventory Management Extension"
app_email = "jomondi@nei-ltd.com"
app_license = "agpl-3.0"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "inventory_management_extension",
# 		"logo": "/assets/inventory_management_extension/logo.png",
# 		"title": "Inventory Management Extension",
# 		"route": "/inventory_management_extension",
# 		"has_permission": "inventory_management_extension.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/inventory_management_extension/css/inventory_management_extension.css"
# app_include_js = "/assets/inventory_management_extension/js/inventory_management_extension.js"

# include js, css files in header of web template
# web_include_css = "/assets/inventory_management_extension/css/inventory_management_extension.css"
# web_include_js = "/assets/inventory_management_extension/js/inventory_management_extension.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "inventory_management_extension/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Delivery Note" : "public/js/delivery_note.js",
              "Pick List" : "public/js/pack_list.js",
              "Purchase Receipt" : "public/js/purchase_receipt.js",
              "Stock Entry" : "public/js/stock_entry.js",}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "inventory_management_extension/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

fixtures= [
    {
        "doctype":"Custom Field",
        "filters": [
            [
                "name",
                "in",   
                ("Stock Entry Detail-custom_transaction_barcode",
                 "Serial and Batch Entry-custom_barcode",
                 "Purchase Receipt-custom_transaction_barcode"
                 "Purchase Receipt Item-custom_column_break_ysrh2",
                 "Purchase Receipt Item-custom_transaction_barcode",
                 "Stock Entry Detail-custom_column_break_8o5fo",
                 "Sales Invoice-custom_section_break_wgdnz",
                 "Sales Invoice-custom_batch_barcode",
                 "Pick List-custom_section_break_f4l7m",
                 "Pick List-custom_items",
                 "Purchase Receipt Item-custom_split_no",
                 "Purchase Receipt-custom_split_items",
                 "Stock Entry Detail-custom_split_no",
                 "Stock Entry-custom_split_items",
                 "Stock Entry-custom_create_lot",
                 "Pick List-custom_scan_transactional_barcode",
                 "Item-custom_cubic",
                 "Delivery Note Item-custom_gross_weight",
                "Delivery Note Item-custom_packaging_itemuom",
                 "Delivery Note Item-custom_column_break_smssg",
                 "Delivery Note Item-custom_package_item",
                 "Delivery Note Item-custom_packing_weight_details",
                 "Delivery Note Item-custom_cubic",
                 "Pick List Item-custom_cubic",
                 "Pick List-custom_update_items"
                 
                 )
            ]
        ]
    }
]

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "inventory_management_extension.utils.jinja_methods",
# 	"filters": "inventory_management_extension.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "inventory_management_extension.install.before_install"
# after_install = "inventory_management_extension.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "inventory_management_extension.uninstall.before_uninstall"
# after_uninstall = "inventory_management_extension.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "inventory_management_extension.utils.before_app_install"
# after_app_install = "inventory_management_extension.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "inventory_management_extension.utils.before_app_uninstall"
# after_app_uninstall = "inventory_management_extension.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "inventory_management_extension.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
    "Stock Entry": {
        "before_save": "inventory_management_extension.inventory_management_extension.controllers.stock_entry.before_save",
        "on_submit": "inventory_management_extension.inventory_management_extension.controllers.stock_entry.on_submit"
    },
    "Supplier": {
        "before_save": "inventory_management_extension.inventory_management_extension.controllers.supplier.before_save"
    },
    "Purchase Receipt": {
        "before_save": "inventory_management_extension.inventory_management_extension.controllers.purchase_receipt.before_save",
        "on_submit": "inventory_management_extension.inventory_management_extension.controllers.purchase_receipt.on_submit"
    },
    "Delivery Note":{
        "on_submit": "inventory_management_extension.inventory_management_extension.controllers.delivery_note.before_submit",
        "before_insert": "inventory_management_extension.inventory_management_extension.controllers.delivery_note.before_save"
    },
    "Pick List": {
        "on_submit": "inventory_management_extension.inventory_management_extension.controllers.pick_list.before_submit"
    },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"inventory_management_extension.tasks.all"
# 	],
# 	"daily": [
# 		"inventory_management_extension.tasks.daily"
# 	],
# 	"hourly": [
# 		"inventory_management_extension.tasks.hourly"
# 	],
# 	"weekly": [
# 		"inventory_management_extension.tasks.weekly"
# 	],
# 	"monthly": [
# 		"inventory_management_extension.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "inventory_management_extension.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "inventory_management_extension.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "inventory_management_extension.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["inventory_management_extension.utils.before_request"]
# after_request = ["inventory_management_extension.utils.after_request"]

# Job Events
# ----------
# before_job = ["inventory_management_extension.utils.before_job"]
# after_job = ["inventory_management_extension.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"inventory_management_extension.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

