"""回滚 fix_warehouse_names 对大陆仓库的误改

fix_warehouse_names 最初没有限定公司，把所有仓库的 name 都重排成
"<abbr> - <name>"，导致：
  BJ-CSRH - CSRH  →  CSRH - BJ-CSRH

但大陆仓库的原始格式就是 "<warehouse_name> - <abbr>"，
日本仓库才是 "<abbr> - <warehouse_name>"（Company abbr=ISTK）。

本 patch 把 CSRH 公司的仓库名改回原格式。
"""

import frappe


def execute():
    rows = frappe.db.sql(
        """
        SELECT name, warehouse_name FROM `tabWarehouse`
        WHERE company = %s
        """,
        ("CSRH",),
    )

    for full, wh_name in rows:
        # 大陆格式：<warehouse_name> - <abbr>
        expected = f"{wh_name} - CSRH"

        if full == expected:
            continue
        if frappe.db.exists("Warehouse", expected):
            print(f"! 目标 {expected} 已存在，跳过 {full}")
            continue

        frappe.rename_doc("Warehouse", full, wh_name, force=True, merge=False)
        print(f"✓ {full} → {expected}")


if __name__ == "__main__":
    execute()
