import os

from . import __version__ as app_version

app_name = "j2c_istk"
app_title = "J2C_ISTK"
app_publisher = "Ice"
app_description = "日本中古采购-拆解-跨境销售全流程管理"
app_icon = "octicon octicon-package"
app_color = "grey"
app_email = "admin@motitoo.com"
app_license = "MIT"
required_apps = ["frappe/erpnext"]

# ---------------- Includes ----------------
# include js/css assets in doctype views
# app_include_css = "/assets/j2c_istk/css/j2c_istk.css"

# include js, css files in header of doctype views
# v16：必须显式声明 doctype_js / doctype_css，
# 否则 desk 不会加载 app 里的 JS，前端脚本全部失效。
# 注意路径格式：相对 app 包根（j2c_istk/），即 "public/js/xxx.js"
doctype_js = {
    "Label Print": "public/js/label_print.bundle.js",
    "Customs Declaration": "public/js/customs_declaration.bundle.js",
}
doctype_css = {}
# home_page = "login"
# website_route_rules = [ ]

# ---------------- Installed Apps ----------------
# GitHub template for fields and scripts

# v16 的「All Apps」页面（App 列表）只显示声明了 add_to_apps_screen 的 app。
# 没有这个 hook，app 装了、模块也在，但 All Apps 里看不到入口。
# 参考：erpnext/erpnext/hooks.py、frappe/frappe/hooks.py
add_to_apps_screen = [
    {
        "name": app_name,
        "logo": "/assets/j2c_istk/images/j2c_istk-logo.svg",
        "title": app_title,
        # Workspace「贸易」的路由格式是 /desk/<slug>（frappe/ui/sidebar/sidebar_item.js）
        # 注意不能写 /app/xxx —— 那是 desk 的旧前缀，会重定向。
        "route": "/desk/J2C_ISTK",
        "setup_wizard_text": "J2C_ISTK",
        # 排序：ERPNext 是 1，Framework 是 1000（钉在最后）
        "sequence_id": 10,
    }
]

# --------------- Customizable App Injections ---------------
# allowed_apps = [ ]

# --------------- Jobs Scheduling ---------------
# 注意：不要在这里写 "daily": [] 这种空列表——
# 它会覆盖该 app 在 daily 桶下的全部任务定义。
# 保留未定义状态，等真有定时任务时再加具体条目。
#
# scheduler_events = {
#     "daily": [
#         "j2c_istk.tasks.refresh_market_price",
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
# before_install = "j2c_istk.install.before_install"
# after_install = "j2c_istk.install.after_install"

# ---------------- Website / Password ----------------
# website_route_rules = [ ]
