import os

from . import __version__ as app_version

app_name = "secondtrade"
app_title = "二手贸易管理系统"
app_publisher = "Ice"
app_description = "日本中古采购-拆解-跨境销售全流程管理"
app_icon = "octicon octicon-package"
app_color = "grey"
app_email = "admin@motitoo.com"
app_license = "MIT"
required_apps = ["frappe/erpnext"]

# ---------------- Includes ----------------
# include js/css assets in doctype views
# app_include_css = "/assets/secondtrade/css/secondtrade.css"
# app_include_js = "/assets/secondtrade/js/secondtrade.js"

# include js, css files in header of doctype views
# doctype_js = { }
# doctype_css = { }
# home_page = "login"
# website_route_rules = [ ]

# ---------------- Installed Apps ----------------
# GitHub template for fields and scripts

# --------------- Customizable App Injections ---------------
# allowed_apps = [ ]

# --------------- Jobs Scheduling ---------------
scheduler_events = {
    "daily": [],
    "hourly": [],
}

# ---------------- Testing ---------------
# before_tests = ""

# ---------------- Website / Online Store ----------------
# website_context = { }


# ---------------- Utilities ----------------
# utilities = ["icpay", "alipay", "email"]


# ---------------- Installation ----------------
# before_install = "secondtrade.install.before_install"
# after_install = "secondtrade.install.after_install"

# ---------------- Website / Password ----------------
# website_route_rules = [ ]
