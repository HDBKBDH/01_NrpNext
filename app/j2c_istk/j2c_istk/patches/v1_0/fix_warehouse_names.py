"""修正 Warehouse.name 与 warehouse_name 不一致

起因：早期 patch 用了 db.set_value 改 warehouse_name，
但 Warehouse.name 是主键不会被重算，导致显示还是旧名。

现在的仓库命名（用户确认）：
  ISTK 公司：name = warehouse_name（JP / JP-LOCAL，没有 abbr 前缀）
  CSRH 公司：name = "<warehouse_name> - <abbr>"（BJ-CSRH - CSRH）

两种格式并存，所以不能用统一规则，要按公司分别处理。

踩过的坑：
1. rename_doc 在新旧名相同时抛
   "No changes made because old and new name are the same"
   → 每次 rename 前必须先比较
2. Warehouse 的 name 是主键，db.set_value 改不了它
   → 必须 rename_doc
"""

import frappe


def execute():
    # ── ISTK（日本）公司：name 应等于 warehouse_name ──
    rows = frappe.db.sql(
        """
        SELECT name, warehouse_name FROM `tabWarehouse`
        WHERE company = %s
        """,
        ("ISOTENKAI",),
    )
    for full, wh_name in rows:
        if full == wh_name:
            continue
        if frappe.db.exists("Warehouse", wh_name):
            print(f"! 目标 {wh_name} 已存在，跳过 {full}")
            continue

        frappe.rename_doc("Warehouse", full, wh_name, force=True, merge=False)
        print(f"✓ {full} → {wh_name}")

    # ── CSRH（大陆）公司：name 应为 "<warehouse_name> - <abbr>" ──
    rows = frappe.db.sql(
        """
        SELECT name, warehouse_name FROM `tabWarehouse`
        WHERE company = %s
        """,
        ("CSRH",),
    )
    for full, wh_name in rows:
        expected = f"{wh_name} - CSRH"
        if full == expected:
            continue
        if frappe.db.exists("Warehouse", expected):
            print(f"! 目标 {expected} 已存在，跳过 {full}")
            continue

        frappe.rename_doc("Warehouse", full, wh_name, force=True, merge=False)
        print(f"✓ {full} → {expected}")

    frappe.db.commit()
    print("✓ 完成")


if __name__ == "__main__":
    execute()
