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
# v16：必须显式声明 doctype_js / doctype_css，
# 否则 desk 不会加载 app 里的 JS，前端脚本全部失效。
# 注意路径格式：相对 app 包根（secondtrade/），即 "public/js/xxx.js"
doctype_js = {
    "Label Print": "public/js/label_print.bundle.js",
    "Customs Declaration": "public/js/customs_declaration.bundle.js",
}
doctype_css = {}
# home_page = "login"
# website_route_rules = [ ]

# ---------------- Installed Apps ----------------
# GitHub template for fields and scripts

# --------------- Customizable App Injections ---------------
# allowed_apps = [ ]

# --------------- Jobs Scheduling ---------------
# 注意：不要在这里写 "daily": [] 这种空列表——
# 它会覆盖该 app 在 daily 桶下的全部任务定义。
# 保留未定义状态，等真有定时任务时再加具体条目。
#
# scheduler_events = {
#     "daily": [
#         "secondtrade.tasks.refresh_market_price",
#     ],
#     "hourly": [],
# }

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
