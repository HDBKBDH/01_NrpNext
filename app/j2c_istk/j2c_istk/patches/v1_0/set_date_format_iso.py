"""站点日期格式改为 yyyy-mm-dd

需求（用户确认）：「4 yyyy-mm-dd」
现状：System Settings.date_format = dd-mm-yyyy（显示成 23-10-2026）
影响：全站点所有日期字段，不只入库单
"""

import frappe


def execute():
    ss = frappe.get_single("System Settings")
    old = ss.date_format
    if old == "yyyy-mm-dd":
        print("  . 日期格式已是 yyyy-mm-dd")
        return

    ss.date_format = "yyyy-mm-dd"
    ss.flags.ignore_permissions = True
    ss.save()
    frappe.db.commit()
    print("  ✓ 日期格式: {0} -> yyyy-mm-dd".format(old))
