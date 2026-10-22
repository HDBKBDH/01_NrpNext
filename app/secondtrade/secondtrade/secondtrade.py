import frappe


def scan_warehouses():
    """健康检查：返回仓库数量"""
    return frappe.db.count("Warehouse")
