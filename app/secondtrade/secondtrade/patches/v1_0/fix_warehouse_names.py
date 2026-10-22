"""修正 Warehouse.name 与 warehouse_name 不一致

起因：之前的 patch 用了 db.set_value 改 warehouse_name，
但 Warehouse.name 是主键不会被重算，导致：
  warehouse_name = "JP"
  name          = "JP-ISTK - ISTK"   ← 显示出来还是旧名

本 patch 用 rename_doc 重新对齐。
"""

import frappe


# 只修日本公司（ISOTENKAI）的仓库。
# 大陆仓库（CSRH）的 name 格式本来是 "<warehouse_name> - <abbr>"，
# 与日本仓库相反，不要动——否则会造成大面积无意义改名。
TARGET_COMPANY = "ISOTENKAI"


def execute():
    rows = frappe.db.sql(
        """
        SELECT name, warehouse_name, company
        FROM `tabWarehouse`
        WHERE company = %s
        """,
        (TARGET_COMPANY,),
    )

    for full, wh_name, company in rows:
        abbr = frappe.db.get_value("Company", company, "abbr")
        expected = f"{abbr} - {wh_name}"

        if full == expected:
            continue

        # 目标已存在则跳过（不合并，避免意外）
        if frappe.db.exists("Warehouse", expected):
            print(f"! 目标 {expected} 已存在，跳过 {full}")
            continue

        frappe.rename_doc(
            "Warehouse", full, wh_name, force=True, merge=False
        )
        print(f"✓ {full} → {expected}")


if __name__ == "__main__":
    execute()
