"""初始化贸易配置（单例）"""

import frappe


def execute():
    ts = frappe.get_single("Trade Settings")
    ts.capital_cost_rate = 8.0
    ts.holding_cost_start = "PurchaseDate"
    ts.jpy_reference_rate = 0.043
    ts.hkd_reference_rate = 0.92
    ts.save(ignore_permissions=True)
    print("  ✓ Trade Settings 初始化完成（资金成本率 8%）")
